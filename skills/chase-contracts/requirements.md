# From requirements to contracts

This is a basic translation from natural-language requirements to contracts.
The translation can be wrong: a requirement can be ambiguous, and a formula
that passes every check can still say something else than the user meant.
Tell the user that they must read and confirm every formula, and do not
present the contracts as verified requirements until they have.

## 1. Variables

List every signal the requirements talk about, in a table:

| name | type | controlled by | meaning |
|---|---|---|---|
| `req1` | bool | Robot1 (output) | robot 1 asks for the charger |
| `level1` | [0, 10] | environment (input) | battery of robot 1, in tenths |

- Every variable is controlled by one component (an output) or by the
  environment (an input of every component that reads it). Ask the user when
  this is not clear from the requirements; it decides whether a requirement
  is an assumption or a guarantee.
- Use `bool` when the requirements only test a condition ("the battery is
  low"). Use a bounded integer when they count or compare discrete values
  (a mode, a number of robots), and always give the range: an integer
  without a range is 0..16 in the CHASE language. Keep the ranges small.
- Use `real` for physical quantities (a speed, a pressure) compared with
  thresholds. Compare them with constants where the requirement allows it
  (`kias > 40` rather than `kias > limit`): then synthesis works too.
- Use the names of the user, made valid (no spaces, not a keyword such as
  `G`, `F`, `X`, `P`).

## 2. Predicates

Give each condition that the requirements use a short definition and say
what it means, e.g. `low1 := level1 <= 2` ("the battery of robot 1 is low").
Do not choose thresholds yourself: ask, or keep the condition as a boolean
input. Write the formulas with these definitions expanded.

## 3. One requirement, one formula

Number the requirements (R1, R2, ...) and keep the number with the formula
until the end. A requirement on several components gets one copy per
component (R2.1 for Robot1, R2.2 for Robot2). CHASE splits a top-level
conjunction into separate terms: write `!grant1 & !grant2` as two formulas
R5a and R5b from the start. First restate each requirement as a structured
sentence, in the style of FRET:

    [scope] [when CONDITION] COMPONENT shall [TIMING] satisfy RESPONSE

where TIMING is one of: always, never, initially, at the next step,
eventually, until, before. Then pick the pattern:

| Pattern | Sentence | LTL | GR(1) form |
|---|---|---|---|
| initially | initially p | `p` | the same (initial term) |
| universality | always p | `G p` | the same (safety) |
| absence | never p | `G !p` | the same (safety) |
| next | when p, at the next step q | `G (p -> X q)` | the same (safety) |
| invariance | when p, q | `G (p -> q)` | the same (safety) |
| recurrence | infinitely often p | `G F p` | the same (liveness) |
| response | when p, eventually q | `G (p -> F q)` | see below |
| existence | eventually p | `F p` | see below |
| precedence | p only after q | `!p W q` | see below |
| bounded response | when p, q within n steps | `G (p -> (q \| X q \| X X q ...))` | needs a counter; use the model checker tools |

Response, existence, and precedence are not GR(1) formulas. Keep the LTL
formula for `refines` and `verify`. For `is_realizable` and `synthesize`,
either:

- use `G F (q | !p)` for response when p stays true until q (e.g. a request
  is held until granted); say so to the user, it is weaker otherwise; or
- add an output variable that records the past, and ask the user first,
  because it adds a variable to the component:
  - response, with `pending` (p seen and q not since):
    `pending <-> (p & !q)`, `G (pending' <-> ((p' | pending) & !q'))`,
    `G F !pending`
  - existence, with `seen` (p has held):
    `seen <-> p`, `G (seen' <-> (seen | p'))`, `G F seen`
  - precedence, with `seen` (q has held before):
    `!seen`, `G (seen' <-> (seen | q))`, `G ((!seen & !q) -> !p)`

## 4. Assumptions or guarantees

A requirement is a guarantee of the component that controls its response.
It is also an assumption of a component that reads it only when that
component needs it to keep its own guarantees: "the robot drops its request
after a grant" is a guarantee of Robot1, and an assumption of the arbiter
only if the arbiter cannot serve both robots without it. Do not copy every
guarantee into the assumptions of the readers.

This matters when components feed each other (the arbiter reads `req1`,
Robot1 reads `grant1`). If each assumes what the other guarantees, the
composition allows both to fail together: Robot1 breaks its guarantee, so
the arbiter is excused, stops granting, and Robot1 is excused in turn.
`refines` then fails on the assumptions or the guarantees with such a trace.
Remove the assumption the component does not need (check with
`is_realizable` that it is still realizable without it), or make one of the
two depend only on the inputs of the system.

For GR(1), the initial assumptions read only inputs, and the safety
assumptions read the next value of inputs only (`G (grant1 -> X !req1)` is
fine for the arbiter, whose input is `req1`).

Do not add requirements that the user did not state. If a check needs one
(e.g. an assumption on the environment), propose it as a change and mark it
as added.

## 5. Show the translation

Give the user a table: number, requirement, structured sentence, formula,
assumption or guarantee of which component. For any formula that uses `F`,
`U`, `W`, `R`, or nested `G`, also show an example: `is_satisfiable`
of the formula gives a trace that satisfies it, and `is_satisfiable` of its
negation a trace that violates it. Ask "should this behavior be allowed?".
When two readings are possible, write both and use `implies` to show how
they differ.

## 6. Check

Then follow the workflow of SKILL.md: `verify` with `core: true` on every
contract, and before synthesis `is_realizable`, `is_well_separated`,
`is_vacuous`, and `remove_redundant` with `synth: true`. Report a core by the numbers of the requirements in it,
with their text, not only the formulas. A core has the status `found` (the
terms are in `core`), `none` (the check passes, there is nothing to
explain), or `unknown` (see `reason`). `remove_redundant` does not report
assumptions that a component does not need; see section 4.

Common mistakes:

- `G p -> q` is `(G p) -> q`; write `G (p -> q)`.
- `X` inside a comparison: write `x' = 3`, not `X x = 3`.
- An assumption that reads the next value of an output: the environment
  cannot react to what the component does in the same step.
- Contradictory assumptions: every refinement then holds. Check that the
  composite is still compatible.
- `G (p -> q)` where the assumptions say that p never happens: the
  requirement obliges nothing; `remove_redundant` reports it.
