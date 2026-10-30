# GR(1) realizability and synthesis

## Before synthesis

For each component to synthesize:

- `is_realizable` with `core: true`: if unrealizable, the core names the
  guarantees that conflict, and the counter-strategy shows how the
  environment wins; weaken one of them or add the assumption that is
  missing.
- `is_well_separated`: if not separated, the controller can satisfy the
  contract by forcing the environment to break its assumptions instead of
  serving it, while keeping its initial and safety guarantees. Weaken the
  assumptions in the core, or make them depend less on the outputs (e.g.
  "after a grant of the request" rather than "after any grant").
- `is_vacuous`: if vacuous, the controller can win without an output that
  a liveness guarantee asks for (never, or from some step on): the
  assumptions in the core already make the guarantee hold. The guarantee
  obliges nothing; usually an assumption is too strong (e.g. "the robot
  stops asking on its own" instead of "after a grant").
- `remove_redundant` with `synth: true`: drops the terms that are
  redundant in the GR(1) game (implied by others without changing the
  synthesis problem); report them, they often show a misunderstanding.
- `synthesize` builds the controller, and `is_implementation` with the
  controller (and `is_receptive`) checks it against other contracts.

## The GR(1) fragment

`is_realizable`, `synthesize`, `is_well_separated`, `is_vacuous`,
`unrealizable_core`, and `remove_redundant` with `synth` need formulas in the GR(1) fragment: initial conditions
without temporal operators, safety `G (...)` over the current and next
values (`x'` or `X x`), and liveness `G F (...)`. In addition, the initial
assumptions can only read inputs, and the safety assumptions can only read
the next value of inputs: the environment cannot depend on what the
component does next. A pattern such as `G (req -> F grant)` is not GR(1);
`G F (grant | !req)` often says what is meant. When a contract is not in
this form the result is `unknown` with the reason, naming the term; rewrite
it, or use the model checker based tools instead. Temporal operators apply
to formulas: write `x'`, not `X x`, inside a comparison or arithmetic.
