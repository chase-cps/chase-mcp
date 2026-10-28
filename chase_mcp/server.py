"""MCP server exposing the contract operations of CHASE as tools.

A contract is given as JSON::

    {"name": "Arbiter",
     "inputs": {"req": "bool", "n": [0, 3]},
     "outputs": {"grant": "bool"},
     "assumptions": ["G F !req"],
     "guarantees": ["G (req -> F grant)"]}

Variables are Boolean ("bool"), bounded integers [low, high], reals
("real"), or words ("word[8]", "signed word[8]": bit vectors whose arithmetic
wraps around). Formulas use the standard LTL syntax: ! & | -> <-> G F X U R
W, relations (= != < <= > >=), arithmetic (+ - * /), numbers such as 20.5,
and x' for the value of x in the next step; on words also x[7:0], x[3], ::,
<< >>, mod, and the bitwise & | xor !.
"""

from __future__ import annotations

import functools
import os
import sys
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

import chase_cps
from chase_cps import Contract, ltl
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from chase_mcp import __version__

Word = Annotated[str, Field(pattern=r"^(signed |unsigned )?word\[[1-9][0-9]*\]$")]
VarType = Union[Literal["bool", "real"], tuple[int, int], Word]
Backend = Literal["auto", "nuxmv", "nusmv", "nuxmv/ic3", "nuxmv/bdd", "nuxmv/bmc",
                  "nuxmv/portfolio", "nusmv/bdd", "nusmv/bmc"]


class ContractSpec(BaseModel):
    """An assume-guarantee contract over LTL."""
    name: str = Field("C", description="Contract name (letters, digits, _)")
    inputs: dict[str, VarType] = Field(default_factory=dict,
                                       description='Input variables: "bool", [low, high], "real", '
                                                   'or "word[n]" ("signed word[n]")')
    outputs: dict[str, VarType] = Field(default_factory=dict,
                                        description='Output variables: "bool", [low, high], "real", '
                                                    'or "word[n]" ("signed word[n]")')
    assumptions: list[str] = Field(default_factory=list,
                                   description="LTL formulas, read as a conjunction")
    guarantees: list[str] = Field(default_factory=list,
                                  description="LTL formulas, read as a conjunction")

    def build(self) -> Contract:
        try:
            return Contract.from_dict(self.model_dump())
        except ltl.LTLSyntaxError as e:
            raise ValueError(f"syntax error in contract {self.name}: {e}") from None


INSTRUCTIONS = """\
Tools for assume-guarantee contracts in LTL, computed by the CHASE framework
(https://chase-cps.github.io).

A contract (A, G) promises the guarantees G when the environment satisfies the
assumptions A. Contracts are read as saturated: the behaviors allowed are those
of A -> G. Inputs are controlled by the environment, outputs by the component.

Formulas: ! & | -> <-> G F X U R W, true, false, relations = != < <= > >=,
arithmetic + - * /, and x' (the value of x in the next step). Words
("word[8]", "signed word[8]"): bits x[7:0] and x[3], concatenation ::, shifts
<< >>, mod, bitwise & | xor ! (parenthesize them in a relation:
(x & y) = 0); both operands have the same width and signedness, and the
arithmetic wraps around. slugs does not take words. Unary operators
bind tighter than binary ones: G a -> b is (G a) -> b; write G (a -> b).
Names cannot be keywords (G F X U R W true false, and CHASE keywords such as
P, NAME, CONTRACT).

The tools are in three layers:
1. Contract algebra (compose, conjoin, disjoin, merge, divide, separate,
   imply, coimply, invert, assume, ensure, saturate, simplify): they return a
   new contract, and hold for any assume-guarantee contracts.
2. Checks on contracts (refines, verify, is_compatible, is_consistent,
   implements, accepts, is_receptive, remove_redundant), which reduce to queries on
   formulas: implies (validity), is_satisfiable (satisfiability of a
   formula, not the satisfaction of a contract by a component, which is
   implements), and unsat_core. They take a context: formulas that every
   behavior satisfies. implements and accepts also take state machines
   (SMV, a state machine in JSON, or a synthesized controller), and
   is_receptive checks that a machine does not refuse the inputs.
3. GR(1) synthesis with slugs (is_realizable, synthesize, unrealizable_core,
   is_well_separated, is_vacuous): only for contracts in the GR(1) fragment
   of LTL, about whether a component can be synthesized. Before synthesis,
   remove_redundant takes synth: true, which keeps realizability.

The check tools return a status:
valid/invalid for implications, sat/unsat for satisfiability,
realizable/unrealizable, or unknown with a reason (e.g. a timeout). A failed
check comes with a counterexample trace: the states of `prefix`, then the
states of `loop` repeated forever. Use the trace to find which assumption or
guarantee to change.

SystemVerilog: parse_sva reads assume/assert property statements as a contract
(the statements not read are listed with the reason), to_sva writes a
contract as a checker module for any tool that reads SVA. implements,
accepts, and is_receptive take RTL (`rtl`: a Verilog or SystemVerilog
module); rtl_ports gives its ports, the variables of the contracts.

The back end may name the engine of nuXmv: by default IC3 and BDDs run at
the same time ("nuxmv/portfolio"); "nuxmv/ic3", "nuxmv/bdd" (fast when a
counterexample needs a long loop, e.g. a counter that goes around), or
"nuxmv/bmc" (counterexamples only) run one engine.
"""

server = MCPServer(name="chase", instructions=INSTRUCTIONS, version=__version__)

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True,
                            open_world_hint=False)


def _user_errors(fn):
    """Report errors in the given contracts or formulas to the model (the
    server hides the message of other exceptions)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ltl.LTLSyntaxError as e:
            raise ToolError(f"syntax error: {e}") from e
        except (ValueError, RuntimeError, NotImplementedError, OSError) as e:
            raise ToolError(str(e)) from e
    return wrapper


def tool(fn):
    return server.tool(annotations=READ_ONLY)(_user_errors(fn))


def _variables(variables: dict[str, VarType]) -> dict:
    return {k: (v if isinstance(v, str) else tuple(v)) for k, v in variables.items()}


def _fold(contracts: list[ContractSpec], operation: str, name: str | None) -> dict:
    if len(contracts) < 2:
        raise ValueError("give at least two contracts")
    result = contracts[0].build()
    for spec in contracts[1:]:
        result = getattr(result, operation)(spec.build())
    if name:
        result.name = name
    return result.to_dict()


# 1. Contract algebra: operations that build contracts ------------------------

@tool
def compose(contracts: list[ContractSpec], name: str | None = None, discharge: bool = False,
            timeout: float = 60, backend: Backend = "auto") -> dict:
    """Parallel composition of two or more contracts (the contract of the
    system made of the components). Variables with the same name are
    connected; no variable can be an output of two contracts.

    By default the closed form ((A1 & A2) | !(G1 & G2), G1 & G2). With
    discharge, the result keeps the terms of the contracts: an assumption of
    a component implied by the component that drives its inputs is dropped,
    then the redundant terms; each test is one model-checking call. That
    result is an abstraction of the composition: a refinement proved on it
    holds for the composition, a failed one may not."""
    if not discharge:
        return _fold(contracts, "compose", name)
    if len(contracts) < 2:
        raise ValueError("give at least two contracts")
    result = contracts[0].build()
    for spec in contracts[1:]:
        result = result.compose(spec.build(), discharge=True, backend=backend, timeout=timeout)
    if name:
        result.name = name
    return result.to_dict()


@tool
def conjoin(contracts: list[ContractSpec], name: str | None = None) -> dict:
    """Conjunction (greatest lower bound) of two or more contracts: a contract
    that refines all of them, (A1 | A2, G1 & G2)."""
    return _fold(contracts, "conjoin", name)


@tool
def disjoin(contracts: list[ContractSpec], name: str | None = None) -> dict:
    """Disjunction (least upper bound) of two or more contracts: a contract
    refined by all of them, (A1 & A2, G1 | G2)."""
    return _fold(contracts, "disjoin", name)


@tool
def merge(contracts: list[ContractSpec], name: str | None = None) -> dict:
    """Merging of two or more viewpoints of the same component (e.g. function
    and timing): (A1 & A2, (G1 & G2) | !(A1 & A2))."""
    return _fold(contracts, "merge", name)


@tool
def divide(system: ContractSpec, part: ContractSpec, name: str | None = None) -> dict:
    """The contract of the missing component: the largest contract C such that
    part composed with C refines system. (A & G', (G & A') | !(A & G'))."""
    return system.build().divide(part.build(), name).to_dict()


@tool
def separate(system: ContractSpec, part: ContractSpec, name: str | None = None) -> dict:
    """Separation, the adjoint of merging: the smallest contract C such that
    system refines the merging of part and C. ((A & G') | !(G & A'), G & A')."""
    return system.build().separate(part.build(), name).to_dict()


@tool
def imply(premise: ContractSpec, conclusion: ContractSpec, name: str | None = None) -> dict:
    """Implication, the adjoint of conjunction: the largest contract C such
    that the conjunction of C and premise refines conclusion.
    ((A2 & !A1) | (G1 & !G2), G2 | !G1), with premise = (A1, G1)."""
    return premise.build().imply(conclusion.build(), name).to_dict()


@tool
def coimply(first: ContractSpec, second: ContractSpec, name: str | None = None) -> dict:
    """Coimplication, the adjoint of disjunction: the smallest contract C such
    that second refines the disjunction of C and first.
    (A2 | !A1, (G2 & !G1) | (A1 & !A2)), with first = (A1, G1)."""
    return first.build().coimply(second.build(), name).to_dict()


@tool
def invert(contract: ContractSpec, name: str | None = None) -> dict:
    """Reciprocal (G, A): the contract seen from its environment. Inputs
    become outputs and outputs inputs."""
    return contract.build().invert(name).to_dict()


@tool
def assume(contract: ContractSpec, formula: str, name: str | None = None) -> dict:
    """Add an assumption b to the contract: (b & A, b -> G). The result is an
    abstraction of the contract (it is refined by it)."""
    return contract.build().assume(formula, name).to_dict()


@tool
def ensure(contract: ContractSpec, formula: str, name: str | None = None) -> dict:
    """Add a guarantee b to the contract: (b -> A, b & G). The result refines
    the contract."""
    return contract.build().ensure(formula, name).to_dict()


@tool
def saturate(contract: ContractSpec, name: str | None = None) -> dict:
    """Saturation: the equivalent contract (A, A -> G). The other operations
    saturate their operands themselves."""
    return contract.build().saturate(name).to_dict()


@tool
def simplify(contract: ContractSpec, name: str | None = None) -> dict:
    """Simplify the formulas of the contract, as the simplify command of
    logics_tool: negations are moved towards the atoms, and temporal
    operators are grouped (G f & G g becomes G (f & g)). The result is
    equivalent; no model checker is needed."""
    return contract.build().simplify(name).to_dict()


# 2. Checks on contracts ------------------------------------------------------

@tool
def refines(refined: ContractSpec, abstract: ContractSpec, timeout: float = 300,
            backend: Backend = "auto", context: list[str] | None = None) -> dict:
    """Does `refined` refine `abstract` (can it replace it)? Checks that the
    assumptions of `abstract` imply those of `refined`, and that the
    guarantees of `refined` imply those of `abstract`. status is valid,
    invalid (with `failed` and a counterexample trace), or unknown.
    `context`: formulas that every behavior satisfies (e.g. an axiom of an
    encoding, a physical law); the behaviors that violate them are left out."""
    return chase_cps.refines(refined.build(), abstract.build(), backend, context=context,
                             timeout=timeout).to_dict()


@tool
def verify(contract: ContractSpec, core: bool = False, timeout: float = 300,
           backend: Backend = "auto", context: list[str] | None = None) -> dict:
    """Can the assumptions and the guarantees hold together (A & G
    satisfiable, the verify command of logics_tool)? status is that of
    feasible: sat with a witness trace, which also shows compatibility (A
    satisfiable) and consistency (A -> G satisfiable); unsat when the
    guarantees cannot hold when the assumptions do, and then compatible and
    consistent say whether the assumptions alone cannot hold. With core, an
    unsat result carries the terms that conflict (in feasible.core).
    `context`: formulas that every behavior satisfies (e.g. an axiom of an
    encoding, a physical law); the behaviors that violate them are left out."""
    return chase_cps.verify(contract.build(), backend, context=context, core=core,
                            timeout=timeout).to_dict()


@tool
def is_consistent(contract: ContractSpec, core: bool = False, timeout: float = 300,
                  backend: Backend = "auto", context: list[str] | None = None) -> dict:
    """Consistency: is there a behavior allowed by the contract (A -> G
    satisfiable)? sat with a witness trace, or unsat when the guarantees
    contradict each other; with core, the guarantees that contradict each
    other.
    `context`: formulas that every behavior satisfies (e.g. an axiom of an
    encoding, a physical law); the behaviors that violate them are left out."""
    return chase_cps.is_consistent(contract.build(), backend, core=core, context=context,
                                   timeout=timeout).to_dict()


@tool
def is_compatible(contract: ContractSpec, core: bool = False, timeout: float = 300,
                  backend: Backend = "auto", context: list[str] | None = None) -> dict:
    """Compatibility: is there an environment that satisfies the assumptions?
    sat with a witness trace, or unsat when the assumptions contradict each
    other; with core, the assumptions that contradict each other.
    `context`: formulas that every behavior satisfies (e.g. an axiom of an
    encoding, a physical law); the behaviors that violate them are left out."""
    return chase_cps.is_compatible(contract.build(), backend, core=core, context=context,
                                   timeout=timeout).to_dict()


class RTLSpec(BaseModel):
    """A Verilog or SystemVerilog module, read as a state machine with Yosys
    (chase-cps[rtl]): one step is one cycle of the clock, a 1-bit port is a
    Boolean, a wider one a word."""
    top: str = Field(description="The top module")
    files: list[str] = Field(default_factory=list,
                             description="Paths of the source files (Verilog or SystemVerilog)")
    sources: dict[str, str] = Field(default_factory=dict,
                                    description='Source texts by file name, '
                                                '{"fifo.sv": "module fifo ..."}')
    parameters: dict[str, int] = Field(default_factory=dict,
                                       description="Parameters of the top module")
    defines: dict[str, Union[int, str]] = Field(default_factory=dict, description="Macros")
    reset: str | None = Field(None, description='The reset input, "rst" or "!rst_n" '
                              "(active low): it holds in the first step, and the contracts "
                              "are checked from the step after it; it is then not an input")
    names: dict[str, str] = Field(default_factory=dict,
                                  description='Ports renamed as the variables of the '
                                              'contracts, {"ready_and_o": "ready_o"}')
    clocks: list[str] | None = Field(None, description="The clock inputs (default: clk, "
                                     "clk_i, clock), left out")

    def build(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="chase_mcp_rtl_") as tmp:
            files = list(self.files)
            for name, text in self.sources.items():
                path = os.path.join(tmp, os.path.basename(name))
                with open(path, "w") as f:
                    f.write(text)
                files.append(path)
            if not files:
                raise ValueError("give the files or the sources of the RTL")
            options = {"parameters": self.parameters, "defines": self.defines,
                       "reset": self.reset, "names": self.names}
            if self.clocks is not None:
                options["clocks"] = self.clocks
            return chase_cps.Model.from_rtl(files, self.top, **options)


MACHINE_DOC = """The state machine is given as one of: `smv`, a program in SMV (the input
    language of nuXmv: MODULE main with VAR/IVAR, INIT, TRANS..., no
    specification) that declares the variables of the contract; `machine`, a
    state machine in JSON {"name", "inputs", "outputs", "states", "initial",
    "transitions": [{"from", "when", "outputs", "to"}]}: at each step, in its
    state, the machine takes a transition whose `when` (a formula over the
    variables) holds, sets the outputs of that step, and moves to `to`; or
    `controller`, the controller returned by synthesize, with the contract it
    was synthesized from in `synthesized_from` (default: the contract); or
    `rtl`, a Verilog or SystemVerilog module (see rtl_ports for its ports)."""


def _machine_doc(fn):
    """Append the forms of a state machine to the description of the tool."""
    fn.__doc__ = fn.__doc__.rstrip() + "\n    " + MACHINE_DOC
    return fn


def _model(smv, machine, controller, synthesized_from, contract: Contract, rtl=None):
    given = [x for x in (smv, machine, controller, rtl) if x is not None]
    if len(given) > 1:
        raise ValueError("give one of smv, machine, controller, and rtl")
    if rtl is not None:
        return rtl.build()
    if smv is not None:
        return chase_cps.Model.from_smv(smv)
    if machine is not None:
        return chase_cps.Model.from_dict(machine)
    if controller is not None:
        source = synthesized_from.build() if synthesized_from is not None else contract
        return chase_cps.Model.from_controller(controller, source)
    return None


@tool
@_machine_doc
def implements(contract: ContractSpec, implementation: str | None = None,
               smv: str | None = None, machine: dict | None = None,
               controller: dict | None = None, synthesized_from: ContractSpec | None = None,
               rtl: RTLSpec | None = None, timeout: float = 300, backend: Backend = "auto",
               context: list[str] | None = None) -> dict:
    """Does the implementation implement the contract? The implementation is
    an LTL formula (`implementation`): implementation & A -> G must be valid;
    or a state machine, every behavior of which must satisfy A -> G. A
    machine that refuses inputs can implement a contract only because of
    that: check it with is_receptive. valid, or invalid with a trace.
    `context`: formulas that every behavior satisfies (e.g. an axiom of an
    encoding, a physical law); the behaviors that violate them are left out."""
    c = contract.build()
    m = _model(smv, machine, controller, synthesized_from, c, rtl)
    if (m is None) == (implementation is None):
        raise ValueError("give the implementation as a formula or as a state machine")
    return chase_cps.implements(m if m is not None else implementation, c, backend,
                                context=context, timeout=timeout).to_dict()


@tool
def accepts(contract: ContractSpec, environment: str | None = None, smv: str | None = None,
            machine: dict | None = None, rtl: RTLSpec | None = None, timeout: float = 300,
            backend: Backend = "auto", context: list[str] | None = None) -> dict:
    """Does the contract accept the environment? The environment is an LTL
    formula over the variables of the contract (`environment`):
    environment -> A must be valid; or a state machine (`smv`, `machine`, or
    `rtl`, as for implements) every behavior of which must satisfy A.
    `context`: formulas that every behavior satisfies (e.g. an axiom of an
    encoding, a physical law); the behaviors that violate them are left out."""
    c = contract.build()
    m = _model(smv, machine, None, None, c, rtl)
    if (m is None) == (environment is None):
        raise ValueError("give the environment as a formula or as a state machine")
    return chase_cps.accepts(c, m if m is not None else environment, backend,
                             context=context, timeout=timeout).to_dict()


@tool
@_machine_doc
def is_receptive(contract: ContractSpec, smv: str | None = None, machine: dict | None = None,
                 controller: dict | None = None,
                 synthesized_from: ContractSpec | None = None, rtl: RTLSpec | None = None,
                 timeout: float = 300, backend: Backend = "auto") -> dict:
    """Does the state machine accept every input that the assumptions of the
    contract allow? A machine that refuses an input has no behavior with it,
    so implements may hold only because it blocks the inputs. receptive, or
    not_receptive with the trace to the state after which it refuses an
    input (details: state and input). Uses the initial and safety
    assumptions; the inputs must be Boolean or integer ranges."""
    c = contract.build()
    m = _model(smv, machine, controller, synthesized_from, c, rtl)
    if m is None:
        raise ValueError("give the state machine: smv, machine, controller, or rtl")
    return chase_cps.is_receptive(m, c, backend, timeout=timeout).to_dict()


@tool
def remove_redundant(contract: ContractSpec, synth: bool = False, core: bool = False,
                     timeout: float = 60, backend: Backend = "auto",
                     context: list[str] | None = None) -> dict:
    """Drop the assumptions implied by the other assumptions, and the
    guarantees implied by the assumptions and the other guarantees.
    Returns the contract and the terms removed (`removed`: each term with
    its part, and with core the terms that imply it); terms whose check did
    not finish are kept and listed in `unknown`.
    Choose `synth` by what the contract is for next. false (the default)
    keeps A -> G: before the algebra and the checks (compose, refines,
    verify, ...). true keeps realizability and the controllers: before
    synthesis (is_realizable, synthesize, is_well_separated, is_vacuous);
    a term is dropped only when it is implied in the GR(1) game, and each
    removed term has its kind (init, safety, justice). With synth the terms
    must be GR(1), and there is no context. The two differ only when the
    assumptions are wrong (unsatisfiable, or constraining the outputs).
    `context`: formulas that every behavior satisfies (e.g. an axiom of an
    encoding, a physical law); the behaviors that violate them are left out."""
    return chase_cps.remove_redundant(contract.build(), backend, context=context,
                                      synth=synth, core=core, timeout=timeout).to_dict()


# 2. Queries on formulas (validity, satisfiability) ---------------------------

@tool
def implies(phi: str, psi: str, variables: dict[str, VarType], timeout: float = 300,
            backend: Backend = "auto", context: list[str] | None = None) -> dict:
    """On formulas: validity. Is the LTL formula phi -> psi valid, i.e. true
    for every behavior? Returns valid, or invalid with a counterexample trace
    satisfying phi and violating psi.
    `context`: formulas that every behavior satisfies (e.g. an axiom of an
    encoding, a physical law); the behaviors that violate them are left out."""
    return chase_cps.implies(phi, psi, _variables(variables), backend, context=context,
                             timeout=timeout).to_dict()


@tool
def is_satisfiable(formula: str, variables: dict[str, VarType], core: bool = False,
                   timeout: float = 300, backend: Backend = "auto",
                   context: list[str] | None = None) -> dict:
    """On formulas: satisfiability. Does some behavior satisfy the LTL formula?
    sat with a witness trace, or unsat; with core, the conjuncts of the
    formula that cannot hold together. This is not the satisfaction of a
    contract by a component, which is implements.
    `context`: formulas that every behavior satisfies (e.g. an axiom of an
    encoding, a physical law); the behaviors that violate them are left out."""
    return chase_cps.is_satisfiable(formula, _variables(variables), backend, core=core,
                                    context=context, timeout=timeout).to_dict()


@tool
def unsat_core(contract: ContractSpec | None = None, formulas: list[str] | None = None,
               variables: dict[str, VarType] | None = None, timeout: float = 300,
               backend: Backend = "auto", context: list[str] | None = None) -> dict:
    """On formulas: a minimal set of terms that cannot hold together. Give a contract (its
    assumptions and guarantees, A & G, are searched: the core says whether
    the assumptions contradict each other, the guarantees do, or the
    guarantees cannot hold when the assumptions do), or formulas with their
    variables. status is found with core, none when they can hold together,
    or unknown with the reason.
    `context`: formulas that every behavior satisfies (e.g. an axiom of an
    encoding, a physical law); the behaviors that violate them are left out."""
    if (contract is None) == (formulas is None):
        raise ValueError("give either a contract or formulas")
    if contract is not None:
        return chase_cps.unsat_core(contract.build(), backend=backend, context=context,
                                    timeout=timeout).to_dict()
    if variables is None:
        raise ValueError("formulas need their variables")
    return chase_cps.unsat_core(formulas, _variables(variables), backend, context=context,
                                timeout=timeout).to_dict()


# 3. GR(1) synthesis, with slugs ----------------------------------------------

@tool
def is_realizable(contract: ContractSpec, core: bool = False, timeout: float = 300) -> dict:
    """GR(1) synthesis (slugs): realizability. Can a component choose its
    outputs so that the guarantees hold for every environment satisfying the
    assumptions? realizable, or unrealizable with the counter-strategy of the
    environment; with core, also the unrealizable core (see
    unrealizable_core). Needs slugs; the formulas must be in the GR(1)
    fragment."""
    return chase_cps.is_realizable(contract.build(), core=core, timeout=timeout).to_dict()


@tool
def synthesize(contract: ContractSpec, timeout: float = 300) -> dict:
    """GR(1) synthesis (slugs): the controller (an explicit strategy) when the
    contract is realizable, or the counter-strategy of the environment.
    Needs slugs; the formulas must be in the GR(1) fragment."""
    return chase_cps.synthesize(contract.build(), timeout=timeout).to_dict()


@tool
def unrealizable_core(contract: ContractSpec, timeout: float = 300) -> dict:
    """GR(1) synthesis (slugs): a minimal set of guarantees that is unrealizable
    under all the assumptions: removing any of them makes the contract
    realizable. status is found with core (the contract with those
    guarantees), none when the contract is realizable, or unknown with the
    reason. Needs slugs."""
    return chase_cps.unrealizable_core(contract.build(), timeout=timeout).to_dict()


@tool
def is_well_separated(contract: ContractSpec, with_guarantees: bool = True, core: bool = False,
                      timeout: float = 300) -> dict:
    """GR(1) synthesis (slugs): well-separation. Can the component win by
    forcing the environment to violate its assumptions? separated when it cannot;
    not_separated with the controller that forces the violation, which means
    the assumptions are too weak or depend on the outputs; with core, a
    minimal set of assumptions that causes it. The component must keep its
    initial and safety guarantees while it forces the violation (with
    with_guarantees false, the guarantees are left out). Only violations
    forced from every initial state are detected."""
    return chase_cps.is_well_separated(contract.build(), with_guarantees=with_guarantees,
                                       core=core, timeout=timeout).to_dict()


@tool
def is_vacuous(contract: ContractSpec, outputs: list[str] | None = None, core: bool = False,
               timeout: float = 300) -> dict:
    """GR(1) synthesis (slugs): vacuity. Can the component win without an
    output that a liveness guarantee asks for (Bloem et al., FMSD 2021)?
    vacuous lists each such output with its mode, never (a winning strategy
    never sets it: the guarantee that names it is discharged by the
    assumptions) or eventually (a winning strategy stops setting it), and the
    strategy; with core, a minimal set of assumptions that lets it.
    not_vacuous; unrealizable when the contract itself is; unknown. The
    outputs checked are `outputs`, by default those that occur only
    positively in a liveness guarantee (G F ...)."""
    return chase_cps.is_vacuous(contract.build(), outputs=outputs, core=core,
                                timeout=timeout).to_dict()


# Specifications in the CHASE language ---------------------------------------

@tool
def parse_spec(text: str | None = None, path: str | None = None) -> dict:
    """Read the contracts of a specification in the logics language of CHASE
    (the .ltl files of logics_tool), given as text or as a file path."""
    if (text is None) == (path is None):
        raise ValueError("give either text or path")
    found = chase_cps.parse_spec(text) if text is not None else chase_cps.load_spec(path)
    return {"contracts": [c.to_dict() for c in found.values()]}


@tool
def to_spec(contracts: list[ContractSpec], name: str = "spec") -> str:
    """Write contracts as a specification in the logics language of CHASE,
    which logics_tool and the other CHASE tools read."""
    return chase_cps.to_spec([c.build() for c in contracts], name)


@tool
def rtl_ports(rtl: RTLSpec) -> dict:
    """The ports of a Verilog or SystemVerilog module read as a state machine:
    the inputs and the outputs with their types ("bool", "word[n]"), as the
    variables of a contract checked against it, the reset (not an input when
    given), and `start`, the step from which the contracts are checked."""
    m = rtl.build()
    reset = rtl.names.get((rtl.reset or "").lstrip("!").strip(),
                          (rtl.reset or "").lstrip("!").strip()) or None
    inputs = {v: t for v, t in m.variables.items() if v in m.ivars}
    outputs = {v: t for v, t in m.variables.items() if v not in m.ivars and v != reset}
    return {"name": m.name, "inputs": inputs, "outputs": outputs, "reset": reset,
            "start": m.start}


# SystemVerilog Assertions ---------------------------------------------------

@tool
def parse_sva(text: str | None = None, path: str | None = None,
             inputs: list[str] | None = None, outputs: list[str] | None = None,
             name: str | None = None, parameters: dict[str, int] | None = None,
             clock: str | None = None) -> dict:
    """Read the assume property and assert property statements of
    SystemVerilog (a module, a bind file, or the statements alone; text or
    a file path) as a contract: assumptions and guarantees, with the widths
    of Verilog, $past, bounded sequences, and disable iff. The directions
    come from the module ports, or from `inputs` or `outputs` (the other
    signals are of the other kind). Returns the contract, the properties
    read (label, kind, formula, from_cycle: the cycle from which a property
    with $past is checked), `skipped` (statements not read, with the
    reason), `covers`, the `clock`, and `undeclared` (signals read as 1
    bit), and `names` (hierarchical names: u1__state is u1.state; give them
    to to_sva). One clock per contract: `clock` ("posedge clk") chooses it."""
    if (text is None) == (path is None):
        raise ValueError("give either text or path")
    if path is not None:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    r = chase_cps.parse_sva(text, inputs=inputs, outputs=outputs, name=name,
                            parameters=parameters, clock=clock)
    return {"contract": r.contract.to_dict(),
            "properties": [{"label": p.label, "kind": p.kind,
                            "formula": chase_cps.ltl.to_str(p.formula),
                            "from_cycle": p.from_cycle} for p in r.properties],
            "skipped": [{"label": s.label, "text": s.text, "reason": s.reason}
                        for s in r.skipped],
            "covers": r.covers, "clock": r.clock, "undeclared": r.undeclared,
            "names": r.names}


@tool
def to_sva(contract: ContractSpec, clock: str = "clk", edge: str = "posedge",
              reset: str | None = None, module: str | None = None,
              bind: str | None = None, names: dict[str, str] | None = None) -> str:
    """Write a contract as a SystemVerilog checker module: assumptions as
    assume property, guarantees as assert property, clocked by
    @(edge clock); a formula G p is checked at every cycle, any other once
    (initial). `reset` (e.g. "rst" or "!rst_n") disables the properties
    while it holds; `bind`, the name of a design module, adds a bind
    statement (ports connected by name; `names`, from parse_sva, connects
    the hierarchical names). Any tool that reads SVA can check the module.
    Real variables cannot be written."""
    return chase_cps.to_sva(contract.build(), clock=clock, edge=edge, reset=reset,
                            module=module, bind=bind, names=names)


def _protocol_stdout():
    """The CHASE libraries print messages on the standard output, which
    carries the protocol: move file descriptor 1 to the standard error and
    return a stream on the original standard output for the protocol."""
    sys.stdout.flush()
    protocol = os.dup(1)
    os.dup2(2, 1)
    return os.fdopen(protocol, "w", encoding="utf-8")


def main() -> None:
    sys.stdout = _protocol_stdout()
    server.run("stdio")


if __name__ == "__main__":
    main()
