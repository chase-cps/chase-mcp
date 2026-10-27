"""MCP server exposing the contract operations of CHASE as tools.

A contract is given as JSON::

    {"name": "Arbiter",
     "inputs": {"req": "bool", "n": [0, 3]},
     "outputs": {"grant": "bool"},
     "assumptions": ["G F !req"],
     "guarantees": ["G (req -> F grant)"]}

Variables are Boolean ("bool"), bounded integers [low, high], or reals
("real"). Formulas use the standard LTL syntax: ! & | -> <-> G F X U R W,
relations (= != < <= > >=), arithmetic (+ - * /), numbers such as 20.5, and
x' for the value of x in the next step.
"""

from __future__ import annotations

import functools
import os
import sys
from typing import Literal, Union

from pydantic import BaseModel, Field

import chase_cps
from chase_cps import Contract, ltl
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from chase_mcp import __version__

VarType = Union[Literal["bool", "real"], tuple[int, int]]
Backend = Literal["auto", "nuxmv", "nusmv"]


class ContractSpec(BaseModel):
    """An assume-guarantee contract over LTL."""
    name: str = Field("C", description="Contract name (letters, digits, _)")
    inputs: dict[str, VarType] = Field(default_factory=dict,
                                       description='Input variables: "bool", [low, high], or "real"')
    outputs: dict[str, VarType] = Field(default_factory=dict,
                                        description='Output variables: "bool", [low, high], or "real"')
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
arithmetic + - * /, and x' (the value of x in the next step). Unary operators
bind tighter than binary ones: G a -> b is (G a) -> b; write G (a -> b).
Names cannot be keywords (G F X U R W true false, and CHASE keywords such as
P, NAME, CONTRACT).

The algebra tools return a new contract. The check tools return a status:
valid/invalid for implications, sat/unsat for satisfiability,
realizable/unrealizable, or unknown with a reason (e.g. a timeout). A failed
check comes with a counterexample trace: the states of `prefix`, then the
states of `loop` repeated forever. Use the trace to find which assumption or
guarantee to change.
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
    return {k: (v if v in ("bool", "real") else tuple(v)) for k, v in variables.items()}


def _fold(contracts: list[ContractSpec], operation: str, name: str | None) -> dict:
    if len(contracts) < 2:
        raise ValueError("give at least two contracts")
    result = contracts[0].build()
    for spec in contracts[1:]:
        result = getattr(result, operation)(spec.build())
    if name:
        result.name = name
    return result.to_dict()


# Contract operations that build contracts -----------------------------------

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


@tool
def remove_redundant(contract: ContractSpec, timeout: float = 60,
                     backend: Backend = "auto") -> dict:
    """Drop the assumptions implied by the other assumptions, and the
    guarantees implied by the assumptions and the other guarantees.
    Returns the contract and the terms removed; terms whose check did not
    finish are kept and listed in `unknown`."""
    return chase_cps.remove_redundant(contract.build(), backend, timeout=timeout).to_dict()


@tool
def remove_vacuous(contract: ContractSpec, core: bool = False, timeout: float = 60,
                   backend: Backend = "auto") -> dict:
    """Remove the terms whose removal does not change the GR(1) specification
    (its realizability and controllers): inherent vacuity, Maoz and Shalom
    2020. Returns the contract and the removed terms in order, each with its
    part (assumption or guarantee), its kind (init, safety, justice), and
    with core the terms that make it vacuous. Unlike remove_redundant, which
    keeps A -> G, this keeps the synthesis problem."""
    return chase_cps.remove_vacuous(contract.build(), core=core, backend=backend,
                                    timeout=timeout).to_dict()


# Contract operations that check contracts -----------------------------------

@tool
def refines(refined: ContractSpec, abstract: ContractSpec, timeout: float = 300,
            backend: Backend = "auto") -> dict:
    """Does `refined` refine `abstract` (can it replace it)? Checks that the
    assumptions of `abstract` imply those of `refined`, and that the
    guarantees of `refined` imply those of `abstract`. status is valid,
    invalid (with `failed` and a counterexample trace), or unknown."""
    return chase_cps.refines(refined.build(), abstract.build(), backend,
                             timeout=timeout).to_dict()


@tool
def verify(contract: ContractSpec, timeout: float = 300,
           backend: Backend = "auto") -> dict:
    """Compatibility and consistency of the contract (the verify command of
    logics_tool): status is sat when both hold; the results of the two checks
    are in compatible and consistent."""
    return chase_cps.verify(contract.build(), backend, timeout=timeout).to_dict()


@tool
def is_consistent(contract: ContractSpec, core: bool = False, timeout: float = 300,
                  backend: Backend = "auto") -> dict:
    """Consistency: is there a behavior allowed by the contract (A -> G
    satisfiable)? sat with a witness trace, or unsat when the guarantees
    contradict each other; with core, the guarantees that contradict each
    other."""
    return chase_cps.is_consistent(contract.build(), backend, core=core,
                                   timeout=timeout).to_dict()


@tool
def is_compatible(contract: ContractSpec, core: bool = False, timeout: float = 300,
                  backend: Backend = "auto") -> dict:
    """Compatibility: is there an environment that satisfies the assumptions?
    sat with a witness trace, or unsat when the assumptions contradict each
    other; with core, the assumptions that contradict each other."""
    return chase_cps.is_compatible(contract.build(), backend, core=core,
                                   timeout=timeout).to_dict()


@tool
def is_realizable(contract: ContractSpec, core: bool = False, timeout: float = 300) -> dict:
    """GR(1) realizability with slugs: can a component choose its outputs so
    that the guarantees hold for every environment satisfying the
    assumptions? realizable, or unrealizable with the counter-strategy of the
    environment; with core, also the unrealizable core (see
    unrealizable_core). Needs slugs; the formulas must be in the GR(1)
    fragment."""
    return chase_cps.is_realizable(contract.build(), core=core, timeout=timeout).to_dict()


@tool
def is_well_separated(contract: ContractSpec, with_guarantees: bool = False, core: bool = False,
                      timeout: float = 300) -> dict:
    """Well-separation (GR(1), slugs): can the component win by forcing the
    environment to violate its assumptions? separated when it cannot;
    not_separated with the controller that forces the violation, which means
    the assumptions are too weak or depend on the outputs; with core, a
    minimal set of assumptions that causes it. With with_guarantees the
    component must keep its initial and safety guarantees. Only violations
    forced from every initial state are detected."""
    return chase_cps.is_well_separated(contract.build(), with_guarantees=with_guarantees,
                                       core=core, timeout=timeout).to_dict()


@tool
def unrealizable_core(contract: ContractSpec, timeout: float = 300) -> dict:
    """A minimal set of guarantees that is unrealizable under all the
    assumptions: removing any of them makes the contract realizable. status
    is found with core (the contract with those guarantees), none when the
    contract is realizable, or unknown with the reason. Needs slugs."""
    return chase_cps.unrealizable_core(contract.build(), timeout=timeout).to_dict()


@tool
def unsat_core(contract: ContractSpec | None = None, formulas: list[str] | None = None,
               variables: dict[str, VarType] | None = None, timeout: float = 300,
               backend: Backend = "auto") -> dict:
    """A minimal set of terms that cannot hold together. Give a contract (its
    assumptions and guarantees, A & G, are searched: the core says whether
    the assumptions contradict each other, the guarantees do, or the
    guarantees cannot hold when the assumptions do), or formulas with their
    variables. status is found with core, none when they can hold together,
    or unknown with the reason."""
    if (contract is None) == (formulas is None):
        raise ValueError("give either a contract or formulas")
    if contract is not None:
        return chase_cps.unsat_core(contract.build(), backend=backend,
                                    timeout=timeout).to_dict()
    if variables is None:
        raise ValueError("formulas need their variables")
    return chase_cps.unsat_core(formulas, _variables(variables), backend,
                                timeout=timeout).to_dict()


@tool
def synthesize(contract: ContractSpec, timeout: float = 300) -> dict:
    """GR(1) synthesis with slugs: the controller (an explicit strategy) when
    the contract is realizable, or the counter-strategy of the environment.
    Needs slugs; the formulas must be in the GR(1) fragment."""
    return chase_cps.synthesize(contract.build(), timeout=timeout).to_dict()


@tool
def accepts(contract: ContractSpec, environment: str, timeout: float = 300,
            backend: Backend = "auto") -> dict:
    """Does the contract accept the environment (an LTL formula over the
    variables of the contract), i.e. environment -> A?"""
    return chase_cps.accepts(contract.build(), environment, backend,
                             timeout=timeout).to_dict()


@tool
def implements(implementation: str, contract: ContractSpec, timeout: float = 300,
               backend: Backend = "auto") -> dict:
    """Does the implementation (an LTL formula describing the behaviors of a
    component) implement the contract, i.e. implementation & A -> G?"""
    return chase_cps.implements(implementation, contract.build(), backend,
                                timeout=timeout).to_dict()


# LTL formulas ---------------------------------------------------------------

@tool
def implies(phi: str, psi: str, variables: dict[str, VarType], timeout: float = 300,
            backend: Backend = "auto") -> dict:
    """Is the LTL formula phi -> psi valid? Returns valid, or invalid with a
    counterexample trace satisfying phi and violating psi."""
    return chase_cps.implies(phi, psi, _variables(variables), backend,
                             timeout=timeout).to_dict()


@tool
def is_satisfiable(formula: str, variables: dict[str, VarType], core: bool = False,
                   timeout: float = 300, backend: Backend = "auto") -> dict:
    """Is the LTL formula satisfiable? sat with a witness trace, or unsat;
    with core, the conjuncts of the formula that cannot hold together."""
    return chase_cps.is_satisfiable(formula, _variables(variables), backend, core=core,
                                    timeout=timeout).to_dict()


# Specifications in the CHASE language ---------------------------------------

@tool
def read_spec(text: str | None = None, path: str | None = None) -> dict:
    """Read the contracts of a specification in the logics language of CHASE
    (the .ltl files of logics_tool), given as text or as a file path."""
    if (text is None) == (path is None):
        raise ValueError("give either text or path")
    found = chase_cps.parse_spec(text) if text is not None else chase_cps.load_spec(path)
    return {"contracts": [c.to_dict() for c in found.values()]}


@tool
def write_spec(contracts: list[ContractSpec], name: str = "spec") -> str:
    """Write contracts as a specification in the logics language of CHASE,
    which logics_tool and the other CHASE tools read."""
    return chase_cps.to_spec([c.build() for c in contracts], name)


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
