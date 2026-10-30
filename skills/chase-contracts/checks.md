# Reading the results and changing contracts

What a result of `refines` says, and which operation to use for each
change of a contract.

## Results of a refinement

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
  use nuXmv (`backend: "nuxmv"`), or reduce the integer ranges. nuXmv
  runs IC3 and BDDs at the same time by default; one engine can be
  chosen with `backend: "nuxmv/ic3"`, `"nuxmv/bdd"`, `"nuxmv/bmc"`.

## Missing components

`divide(system, part)` (the quotient) gives the
contract of the component still to design: the largest contract that,
composed with `part`, refines `system`. `is_realizable` tells whether it
can be implemented (or gives a counter-strategy of the environment), and
`synthesize` builds the controller. Pass `discharge: true` before these:
the closed form is not GR(1), the terms often are.

## Implementations and environments

When the user has a component
already, as a state machine (an SMV model, a state machine in JSON, or a
controller from `synthesize`) or as a formula of its behaviors, use
`is_implementation(implementation, c)`: every behavior must satisfy A -> G. For
a state machine also run `is_receptive`: a machine that refuses some
inputs implements the contract only because those inputs never happen;
the result gives the state and the input it refuses. When the component
is placed in an environment (another component, an operating scenario),
use `is_environment(environment, c)`: every behavior of the environment must
satisfy the assumptions. An invalid result gives the environment
behavior that the component does not expect.

## Viewpoints

Use `merge` for different aspects of the same component
(function, timing, safety), and `separate` to remove a viewpoint. With
`discharge: true`, the merge keeps the terms of the viewpoints (the same
contract), as `is_realizable` and `synthesize` need. Each viewpoint then
holds under the assumptions of all of them. Use `conjoin` when each
specification must hold under its own assumptions (with `discharge: true`
it keeps the terms too; with the same assumptions it is (A, G1 & G2)), and
`disjoin` for a contract that either of two specifications satisfies
(two acceptable variants, such as two operating modes).

## Changing a contract

- `assume` with a formula b: the component is responsible only when b
  holds (an operating mode, a range of the inputs); the result is an
  abstraction of the contract. `ensure` with b adds the guarantee b; the
  result refines the contract.
- `invert`: the contract seen from the environment, with inputs and
  outputs swapped: what the environment must guarantee and may assume.
  Use it to write the contract that a neighbor component must meet.
- `imply` with premise c1 and conclusion c2: the largest contract C such
  that C and c1 together (conjunction) refine c2: what must be added to
  the specification c1 to meet c2. It is to conjunction what `divide` is to composition.
  `coimply` is the adjoint of `disjoin`; it is rarely needed.

## Clean up

`remove_redundant` drops the terms implied by the others.
Choose `synth` by what the contract is for next:

| Next | `synth` | Keeps |
|---|---|---|
| algebra and checks (compose, refines, verify, ...) | false (default) | A -> G |
| synthesis (is_realizable, synthesize, ...) | true | realizability and the controllers |

The two differ only when the assumptions are wrong (unsatisfiable, or
constraining the outputs); then each one can change what the other
keeps. If the contract is for both, or you are not sure, do not remove
anything. `simplify` rewrites the formulas into a shorter equivalent form.
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
