---
name: chase-contracts
description: Write, check, diagnose, and fix assume-guarantee contracts in LTL with CHASE. Use when the user wants to formalize requirements of a system or component as contracts, check that component contracts refine a system contract, find the contract of a missing component (quotient), merge or separate viewpoints, check consistency, compatibility, GR(1) realizability, well-separation, or vacuity, check a state machine (SMV, JSON, or a synthesized controller) against a contract and its receptiveness, find which terms cause a failure (unsat or unrealizable core), remove redundant terms, synthesize a controller, explain a counterexample from these checks, decompose a system into parts and repair the contracts that fail, or draw contracts, refinements, and the results of the checks as a diagram.
---

# Assume-guarantee contracts with CHASE

CHASE (https://chase-cps.github.io) represents requirements as assume-guarantee
contracts over LTL and checks them with a model checker (nuXmv) or a
GR(1) synthesis tool (slugs).

## Tools

Use the tools of the `chase` MCP server when they are available. Otherwise use
the Python package `chase_cps` (`pip install chase-cps`):

The tools are in three layers. Keep them apart when you explain a result:
a failed GR(1) check says that no controller can be synthesized from the
contract, not that the contract is wrong in general.

| MCP tool | Python |
|---|---|
| **1. Contract algebra: operations that build contracts** | |
| `compose`, `conjoin`, `disjoin`, `merge` | `c1.compose(c2)`, `c1.conjoin(c2)`, `c1.disjoin(c2)`, `c1.merge(c2)` |
| `divide` (quotient), `separate` | `system.divide(part)`, `system.separate(part)` |
| `imply`, `coimply`, `invert` | `c1.imply(c2)`, `c1.coimply(c2)`, `c.invert()` |
| `assume`, `ensure` | `c.assume("G F req")`, `c.ensure("G (grant -> X !grant)")` |
| `saturate`, `simplify` | `c.saturate()`, `c.simplify()` |
| **2. Checks on contracts (nuXmv)** | |
| `refines` | `chase_cps.refines(refined, abstract)` |
| `verify`, `is_compatible`, `is_consistent` | `chase_cps.verify(c)`, `chase_cps.is_compatible(c)`, `chase_cps.is_consistent(c)` |
| `is_implementation`, `is_environment` | `chase_cps.is_implementation(implementation, c)`, `chase_cps.is_environment(environment, c)`: a formula or a state machine |
| `is_receptive` | `chase_cps.is_receptive(model, c)` |
| `remove_redundant` | `chase_cps.remove_redundant(c)` |
| **2. Queries on formulas** | |
| `implies` (validity), `is_satisfiable` | `chase_cps.implies(phi, psi, variables)`, `chase_cps.is_satisfiable(phi, variables)` |
| `unsat_core` | `chase_cps.unsat_core(c)`; or `core=True` on the checks |
| **3. GR(1) synthesis (slugs)** | |
| `is_realizable`, `synthesize` | `chase_cps.is_realizable(c)`, `chase_cps.synthesize(c)` |
| `unrealizable_core` | `chase_cps.unrealizable_core(c)`; or `core=True` on `is_realizable` |
| `is_well_separated`, `is_vacuous` | `chase_cps.is_well_separated(c)`, `chase_cps.is_vacuous(c)` |
| **Specifications in the CHASE language** | |
| `parse_spec`, `to_spec` | `chase_cps.load_spec(path)`, `chase_cps.parse_spec(text)`, `chase_cps.to_spec(contracts)` |
| **SystemVerilog Assertions** | |
| `parse_sva`, `to_sva` | `chase_cps.parse_sva(text)`, `chase_cps.to_sva(contract)` |
| `rtl_ports`; `rtl` in `is_implementation`, `is_environment`, `is_receptive` | `chase_cps.Model.from_rtl(files, top)` |
| **Diagrams** | |
| `visualize` | `chase_cps.viz.from_spec(path)`, `chase_cps.viz.diagram(...)`, `chase-cps view FILE` |

The operations that build contracts return a new contract. The checks return
a status and, when they fail, a counterexample. `implies` checks validity
(true for every behavior); `is_satisfiable` checks that some behavior
satisfies a formula, which is not the satisfaction of a contract by a
component (`is_implementation`). With `core: true`, `verify`, `is_realizable`,
`is_compatible`, `is_consistent`, `is_satisfiable`, `is_well_separated`,
and `is_vacuous` also return a core: the few terms that cause the failure
(for `is_vacuous`, the assumptions that let the component win without the
output).

In Python a contract is built with
`Contract.from_dict(d)` or `Contract.from_strings(inputs=..., outputs=..., assumptions=..., guarantees=..., name=...)`.
If the checks fail with "no model checker found", tell the user to install
nuXmv: `chase-cps install nuxmv --accept-license` (free for academic and
non-commercial use), or set `CHASE_NUXMV` to the executable.

## Contracts

```json
{"name": "Arbiter",
 "inputs": {"req": "bool", "n": [0, 3]},
 "outputs": {"grant": "bool"},
 "assumptions": ["G F !req"],
 "guarantees": ["G (req -> F grant)"]}
```

- Inputs are controlled by the environment, outputs by the component.
  Variables are `"bool"`, bounded integers `[low, high]`, `"real"`, or words
  `"word[n]"` (`"signed word[n]"`); keep the integer ranges small, the
  checks get slower with large ranges.
- Real variables: when they are only compared with constants
  (`kias > 40`) or with each other (`kias = kgs`), every check works,
  synthesis too, and the result says `reals: "regions"`. With arithmetic between them (`ia - ib > T`) the model
  checker checks them (`reals: "smt"`, nuXmv only), but realizability and
  synthesis are unknown. With nonlinear arithmetic (`x * y`) the answer may
  be unknown; with `reals: "predicates"` a valid or unsat answer holds, and
  the others come with the reason.
- Assumptions are what the component expects of its environment; guarantees
  are what it promises when the assumptions hold. Both lists are read as
  conjunctions.
- Contracts are read as saturated: the allowed behaviors are those of
  A -> G. A contract with false assumptions allows everything.
- Variables with the same name in two contracts are the same variable: this
  is how components are connected. No variable can be an output of two
  composed contracts.

## Formulas

`! & | -> <->`, `G F X U R W`, `true false`, relations `= != < <= > >=`,
arithmetic `+ - * /`, numbers such as `20.5`, and `x'` for the value of `x`
in the next step.
Unary operators bind tighter than binary ones: `G a -> b` means
`(G a) -> b`; write `G (a -> b)`.

Names cannot be keywords: `G F X U R W true false`, and CHASE keywords such as
`P`, `NAME`, `CONTRACT`, `integer`. Use `p1`, `ready`, and so on.

A formula that holds for every behavior that can happen at all, and is
neither an assumption nor a guarantee of a component (a physical law, "one
tool call at each step", the axiom of an encoding of finite traces), goes in
`context` of the checks (`verify`, `refines`, `implies`, `unsat_core`, ...).
Do not write it as an assumption: a behavior that violates an assumption
satisfies the contract, so `verify` would still find it.

## Workflow

1. **Write the contracts.** One contract per component, and one for the whole
   system. Keep each requirement as a separate formula: the checks and
   `remove_redundant` work term by term. When starting from natural-language
   requirements, follow `requirements.md`: variables and who controls them,
   predicates, one pattern per requirement, and a table of the translation
   that the user must confirm.
2. **Sanity checks.** Run `verify` on every contract: it checks that the
   assumptions and the guarantees can hold together (A & G satisfiable),
   which implies that the contract is compatible (some environment
   satisfies the assumptions) and consistent (some behavior satisfies
   A -> G). An unsat result means contradictory assumptions, or guarantees
   that cannot hold when the assumptions do; `compatible` and `consistent`
   in the result say which. A contract can be compatible and consistent and
   still fail `verify`: A -> G holds whenever the environment breaks A.
   A verified contract can still be unrealizable: `verify` only says
   that some environment and some component agree. Use `is_realizable` when
   the question is whether a component can be built. When a check fails,
   pass `core: true` (or call `unsat_core` / `unrealizable_core`) to get the
   few terms that cause it, and show those to the user rather than the whole
   contract.
3. **Compose and refine.** Compose the component contracts and check that the
   result refines the system contract (`refines`). With `discharge`, the
   composite keeps the terms of the components, which is easier to read and
   often faster to check, and the assumptions of a component that another
   component guarantees are dropped, also when the components feed each
   other (in one direction only). It is an abstraction of the composition,
   so a `valid` refinement holds, but an `invalid` one must be confirmed on
   the composition without `discharge`.
4. **Read the result and go on** with the file for the task:

   | Task | Read |
   |---|---|
   | requirements in natural language | `requirements.md` |
   | a design with several parts, a missing part, contracts that fail and must be fixed | `design-loop.md` |
   | what a result says; implementations, environments, viewpoints, changing and cleaning up contracts; traces | `checks.md` |
   | realizability, synthesis, well-separation, vacuity; the GR(1) fragment | `synthesis.md` |
   | SystemVerilog Assertions and RTL | `hardware.md` |
   | a diagram | `diagrams.md` |

Do not make a check pass by adding `false` or contradictory assumptions.

## Examples

The `examples` folder contains complete examples. Each file lists the
contracts and the steps: the tool, its arguments (`$Name` is a contract of the
file or the result of an earlier step), the expected result, and a note that
explains it. Read the one closest to the task before starting:

- `arbiter.json`: refinement, and reading a counterexample.
- `pipeline.json`: composition, a failed refinement of the assumptions and
  its fix, vacuity, and the quotient.
- `tank.json`: from natural-language requirements to a contract;
  compatibility, removal of redundant terms, and consistency versus realizability.
- `viewpoints.json`: merging viewpoints, checking an implementation, and
  separation.
- `chase-spec.json`: reading and writing specifications in the CHASE
  language.
- `charger.json`: two robots and an arbiter; an unrealizable core, a
  contract that is not well-separated, vacuity (an arbiter that wins without
  granting), a redundant guarantee, and the composition of components that
  feed each other.
- `algebra.json`: implication, reciprocal and quotient, adding assumptions
  or guarantees, and a contract that is compatible and consistent but fails
  `verify`, with its unsat core.
- `airspeed.json`: requirements with a real variable compared at two steps,
  checked with the SMT engine of nuXmv; the requirements in conflict and a
  behavior with real values.
