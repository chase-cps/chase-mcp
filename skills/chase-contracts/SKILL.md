---
name: chase-contracts
description: Write, check, diagnose, and fix assume-guarantee contracts in LTL with CHASE. Use when the user wants to formalize requirements of a system or component as contracts, check that component contracts refine a system contract, find the contract of a missing component (quotient), merge or separate viewpoints, check consistency, compatibility, GR(1) realizability, or well-separation, find which terms cause a failure (unsat or unrealizable core), remove redundant or vacuous terms, synthesize a controller, or explain a counterexample from these checks.
---

# Assume-guarantee contracts with CHASE

CHASE (https://chase-cps.github.io) represents requirements as assume-guarantee
contracts over LTL and checks them with a model checker (nuXmv) or a
GR(1) synthesis tool (slugs).

## Tools

Use the tools of the `chase` MCP server when they are available. Otherwise use
the Python package `chase_cps` (`pip install chase-cps`):

| MCP tool | Python |
|---|---|
| **Contract operations that build contracts** | |
| `compose`, `conjoin`, `disjoin`, `merge` | `c1.compose(c2)`, `c1.conjoin(c2)`, `c1.disjoin(c2)`, `c1.merge(c2)` |
| `divide` (quotient), `separate` | `system.divide(part)`, `system.separate(part)` |
| `imply`, `coimply`, `invert` | `c1.imply(c2)`, `c1.coimply(c2)`, `c.invert()` |
| `assume`, `ensure` | `c.assume("G F req")`, `c.ensure("G (grant -> X !grant)")` |
| `saturate`, `simplify` | `c.saturate()`, `c.simplify()` |
| `remove_redundant`, `remove_vacuous` | `chase_cps.remove_redundant(c)`, `chase_cps.remove_vacuous(c)` |
| **Contract operations that check contracts** | |
| `refines` | `chase_cps.refines(refined, abstract)` |
| `verify`, `is_compatible`, `is_consistent` | `chase_cps.verify(c)`, `chase_cps.is_compatible(c)`, `chase_cps.is_consistent(c)` |
| `is_realizable`, `synthesize`, `is_well_separated` | `chase_cps.is_realizable(c)`, `chase_cps.synthesize(c)`, `chase_cps.is_well_separated(c)` |
| `accepts`, `implements` | `chase_cps.accepts(c, environment)`, `chase_cps.implements(implementation, c)` |
| **Explanations of a failed check** | |
| `unsat_core`, `unrealizable_core` | `chase_cps.unsat_core(c)`, `chase_cps.unrealizable_core(c)`; or `core=True` on the checks |
| **LTL formulas** | |
| `implies`, `is_satisfiable` | `chase_cps.implies(phi, psi, variables)`, `chase_cps.is_satisfiable(phi, variables)` |
| **Specifications in the CHASE language** | |
| `read_spec`, `write_spec` | `chase_cps.load_spec(path)`, `chase_cps.parse_spec(text)`, `chase_cps.to_spec(contracts)` |

The operations that build contracts return a new contract. The checks return
a status and, when they fail, a counterexample. With `core: true`,
`is_realizable`, `is_compatible`, `is_consistent`, `is_satisfiable`, and
`is_well_separated` also return a core: the few terms that cause the
failure.

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
  Variables are `"bool"` or bounded integers `[low, high]`; keep the ranges
  small, the checks get slower with large ranges.
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
arithmetic `+ - * /`, and `x'` for the value of `x` in the next step.
Unary operators bind tighter than binary ones: `G a -> b` means
`(G a) -> b`; write `G (a -> b)`.

Names cannot be keywords: `G F X U R W true false`, and CHASE keywords such as
`P`, `NAME`, `CONTRACT`, `integer`. Use `p1`, `ready`, and so on.

## Workflow

1. **Write the contracts.** One contract per component, and one for the whole
   system. Keep each requirement as a separate formula: the checks and
   `remove_redundant` work term by term.
2. **Sanity checks.** Run `verify` on every contract: it checks that the
   contract is compatible (some environment satisfies the assumptions) and
   consistent (some behavior satisfies A -> G). An unsat result means contradictory assumptions or guarantees.
   A consistent contract can still be unrealizable: consistency only says
   that some environment and some component agree. Use `is_realizable` when
   the question is whether a component can be built. When a check fails,
   pass `core: true` (or call `unsat_core` / `unrealizable_core`) to get the
   few terms that cause it, and show those to the user rather than the whole
   contract. `unsat_core` of a contract also finds guarantees that cannot
   hold when the assumptions do, which `verify` does not report.
3. **Compose and refine.** Compose the component contracts and check that the
   result refines the system contract (`refines`). With `discharge`, the
   composite keeps the terms of the components, which is easier to read and
   often faster to check, and the assumptions of a component that another
   component guarantees are dropped, also when the components feed each
   other (in one direction only). It is an abstraction of the composition,
   so a `valid` refinement holds, but an `invalid` one must be confirmed on
   the composition without `discharge`.
4. **Read the result.**
   - `valid`: the components meet the system contract. Check that the
     composite is still compatible (`is_compatible`): assumptions that cannot
     be satisfied make every refinement hold vacuously.
   - `invalid`: `failed` says which part fails. For `assumptions`, the trace
     is an environment allowed by the system contract that a component does
     not accept: weaken the component assumptions or strengthen the system
     assumptions. For `guarantees`, the trace is a behavior of the components
     that violates the system guarantees: strengthen a component guarantee,
     or the system contract asks for too much.
   - `unknown`: the check did not finish (see `reason`). Increase `timeout`,
     use nuXmv (`backend: "nuxmv"`), or reduce the integer ranges.
5. **Missing components.** `divide(system, part)` (the quotient) gives the
   contract of the component still to design: the largest contract that,
   composed with `part`, refines `system`. `is_realizable` tells whether it
   can be implemented (or gives a counter-strategy of the environment), and
   `synthesize` builds the controller.
6. **Before synthesis.** For each component to synthesize:
   - `is_realizable` with `core: true`: if unrealizable, the core names the
     guarantees that conflict, and the counter-strategy shows how the
     environment wins; weaken one of them or add the assumption that is
     missing.
   - `is_well_separated` (with `with_guarantees: true` to keep the safety
     guarantees): if not separated, the controller can satisfy the contract
     by forcing the environment to break its assumptions instead of serving
     it. Weaken the assumptions in the core, or make them depend less on the
     outputs (e.g. "after a grant of the request" rather than "after any
     grant").
   - `remove_vacuous`: drops the terms that do not change the synthesis
     problem; report them, they often show a misunderstanding.
   - `synthesize` builds the controller.
7. **Viewpoints.** Use `merge` for different aspects of the same component
   (function, timing, safety), and `separate` to remove a viewpoint.
   Use `conjoin` when several specifications must hold at once.
8. **Clean up.** `remove_redundant` drops the terms implied by the others
   (keeping A -> G); `remove_vacuous` keeps realizability instead;
   `simplify` rewrites the formulas into a shorter equivalent form.
   `saturate` gives the equivalent contract (A, A -> G), e.g. to show the
   user the behaviors a contract allows; the other operations saturate their
   operands themselves.

## Traces

A trace is a list of `prefix` states followed by a `loop` of states repeated
forever. Each state gives the value of every variable. Explain a
counterexample to the user step by step ("at step 2 req is true, and grant
stays false in the loop"), point to the requirement it violates, and propose
a change. Do not make a check pass by adding `false` or contradictory
assumptions.

## Realizability

`is_realizable`, `synthesize`, `is_well_separated`, `unrealizable_core`, and
`remove_vacuous` need formulas in the GR(1) fragment: initial conditions
without temporal operators, safety `G (...)` over the current and next
values (`x'` or `X x`), and liveness `G F (...)`. In addition, the initial
assumptions can only read inputs, and the safety assumptions can only read
the next value of inputs: the environment cannot depend on what the
component does next. A pattern such as `G (req -> F grant)` is not GR(1);
`G F (grant | !req)` often says what is meant. When a contract is not in
this form the result is `unknown` with the reason, naming the term; rewrite
it, or use the model checker based tools instead. Temporal operators apply
to formulas: write `x'`, not `X x`, inside a comparison or arithmetic.

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
  contract that is not well-separated, vacuous terms, and the composition of
  components that feed each other.
- `algebra.json`: implication, reciprocal and quotient, adding assumptions
  or guarantees, and an unsat core of assumptions and guarantees.
