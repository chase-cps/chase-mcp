"""MCP server exposing the contract operations of CHASE as tools.

A contract is given as JSON::

    {"name": "Arbiter",
     "inputs": {"req": "bool", "n": [0, 3]},
     "outputs": {"grant": "bool"},
     "assumptions": ["G F !req"],
     "guarantees": ["G (req -> F grant)"]}

Variables are Boolean ("bool") or bounded integers [low, high]. Formulas use
the standard LTL syntax: ! & | -> <-> G F X U R W, relations (= != < <= > >=),
arithmetic (+ - * /), and x' for the value of x in the next step.
"""

from __future__ import annotations

import functools
from typing import Literal, Union

from pydantic import BaseModel, Field

import chase_cps
from chase_cps import Contract, ltl
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

VarType = Union[Literal["bool"], tuple[int, int]]


class ContractSpec(BaseModel):
    """An assume-guarantee contract over LTL."""
    name: str = Field("C", description="Contract name (letters, digits, _)")
    inputs: dict[str, VarType] = Field(default_factory=dict,
                                       description='Input variables: "bool" or [low, high]')
    outputs: dict[str, VarType] = Field(default_factory=dict,
                                        description='Output variables: "bool" or [low, high]')
    assumptions: list[str] = Field(default_factory=list,
                                   description="LTL formulas, read as a conjunction")
    guarantees: list[str] = Field(default_factory=list,
                                  description="LTL formulas, read as a conjunction")

    def build(self) -> Contract:
        try:
            return Contract.from_dict(self.model_dump())
        except ltl.LTLSyntaxError as e:
            raise ValueError(f"syntax error in contract {self.name}: {e}") from None


server = MCPServer(
    name="chase",
    instructions=(
        "Tools for assume-guarantee contracts in LTL, computed by the CHASE "
        "framework (https://chase-cps.github.io). Build contracts as JSON, "
        "compose them, and check refinement: a failed check returns a "
        "counterexample trace (prefix, then a loop repeated forever) that "
        "shows what to fix."),
)


def _result(r) -> dict:
    return r.to_dict()


def _user_errors(fn):
    """Report errors in the given contracts or formulas to the model (the
    server hides the message of other exceptions)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, RuntimeError, NotImplementedError) as e:
            raise ToolError(str(e)) from e
    return wrapper


@server.tool()
@_user_errors
def compose(contracts: list[ContractSpec], name: str | None = None) -> dict:
    """Parallel composition of two or more contracts. Variables with the same
    name are connected. Returns the composite contract."""
    if len(contracts) < 2:
        raise ValueError("give at least two contracts")
    result = contracts[0].build()
    for spec in contracts[1:]:
        result = result.compose(spec.build())
    if name:
        result.name = name
    return result.to_dict()


@server.tool()
@_user_errors
def quotient(system: ContractSpec, part: ContractSpec, name: str | None = None) -> dict:
    """The contract of the missing component: the quotient system / part, such
    that composing it with part refines system."""
    return system.build().quotient(part.build(), name).to_dict()


@server.tool()
@_user_errors
def separation(system: ContractSpec, part: ContractSpec, name: str | None = None) -> dict:
    """Separation system / part, the adjoint of merging (dual of the quotient)."""
    return system.build().separation(part.build(), name).to_dict()


@server.tool()
@_user_errors
def refine(refined: ContractSpec, abstract: ContractSpec, timeout: float = 300) -> dict:
    """Does `refined` refine `abstract` (can it replace it)? Checks that the
    assumptions of `abstract` imply those of `refined`, and that the
    guarantees of `refined` imply those of `abstract` (both saturated).
    status is valid, invalid (with `failed` and a counterexample trace), or
    unknown (with a reason, e.g. a timeout)."""
    return chase_cps.refines(refined.build(), abstract.build(), timeout=timeout).to_dict()


@server.tool()
@_user_errors
def check(contract: ContractSpec,
          properties: list[Literal["consistent", "compatible", "realizable"]] =
          ["consistent", "compatible"],
          timeout: float = 300) -> dict:
    """Check properties of one contract.
    consistent: some behavior satisfies A -> G (a witness trace is returned).
    compatible: some environment satisfies A.
    realizable: GR(1) realizability with slugs; returns the controller, or the
    environment counter-strategy when unrealizable."""
    c = contract.build()
    out = {}
    for p in properties:
        if p == "consistent":
            out[p] = _result(chase_cps.consistent(c, timeout=timeout))
        elif p == "compatible":
            out[p] = _result(chase_cps.compatible(c, timeout=timeout))
        elif p == "realizable":
            out[p] = _result(chase_cps.realizable(c, timeout=timeout))
    return out


@server.tool()
@_user_errors
def implies(phi: str, psi: str, variables: dict[str, VarType],
            timeout: float = 300) -> dict:
    """Is the LTL formula phi -> psi valid? Returns valid, or invalid with a
    counterexample trace satisfying phi and violating psi."""
    variables = {k: ("bool" if v == "bool" else tuple(v)) for k, v in variables.items()}
    try:
        return _result(chase_cps.implies(phi, psi, variables, timeout=timeout))
    except ltl.LTLSyntaxError as e:
        raise ValueError(f"syntax error: {e}") from None


@server.tool()
@_user_errors
def remove_redundant(contract: ContractSpec, timeout: float = 60) -> dict:
    """Drop the assumptions implied by the other assumptions, and the
    guarantees implied by the assumptions and the other guarantees."""
    return chase_cps.remove_redundant(contract.build(), timeout=timeout).to_dict()


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
