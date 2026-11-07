# Design, decomposition, and repair

Follow this loop when the user designs a system with several parts, or asks
to fix contracts that fail. Each step ends with a check. Do not go to the
next step while the check fails.

## 1. The contract of the system

Write the contract of the whole system first, from the requirements
(`requirements.md`), with only the inputs and outputs it has from the
outside. Run `verify` with `core: true`.

## 2. The parts

Propose the parts, one contract each:

- Each output is driven by one part. A signal between two parts is an
  output of the part that drives it and an input of the parts that read it,
  with the same name.
- Two to five parts on one level. Go down one level at a time: a part with
  parts of its own is the system of the next level.
- Run `verify` on each part.

## 3. The check of the decomposition

`compose` the parts, with `discharge: true` first, and check that the
result `refines` the contract of the system. Check that the composite is
compatible (`is_compatible`). A valid refinement means that the
decomposition is right whatever the parts become later: each part can now
be designed alone against its own contract.

## 4. A part that is not written

When every part but one is written, compute the quotient before you write
anything for the missing part: `divide(system, compose(parts))`, with
`discharge: true`. It is the weakest contract of the part. Use it as the
contract of the part, or check a candidate against it
(`refines(candidate, quotient)`). When the quotient is not GR(1) (`X X p`,
a response within n steps), write a GR(1) candidate with outputs of its
own (a counter), check that it refines the quotient, and run
`is_realizable` on the candidate. A candidate can refine the
quotient without refining the contract of the part it replaces. For a part
to synthesize, run `is_realizable` and then `synthesize` on the quotient,
or on the candidate (`synthesis.md`).

## 5. Repair

When a check fails, change only what the core or the trace points to:

- `refines` invalid with `discharge`: check again without `discharge`
  first; only an invalid result there needs a change.
- `verify` unsat: the core names the terms in conflict. One of them is
  wrong. When the requirements do not say which one, ask the user.
- `refines` invalid with `failed: assumptions`: the trace is an environment
  that the system accepts and a part does not. Weaken the assumption of the
  part, or strengthen the assumption of the system.
- `refines` invalid with `failed: guarantees`: the trace is a behavior of
  the parts that breaks a guarantee of the system. Strengthen a guarantee of
  a part, or the system asks for too much.
- Unrealizable: the core and the counter-strategy (`synthesis.md`). Weaken
  a guarantee in the core, or add the assumption that is missing.
- A conflict about a number (a deadline, a threshold, a range): change the
  number, not the form of the term, and let `repair` find it (below).

### Repair of a number

`repair` finds the values of named constants that make a check pass
(`refines`, `impl`, `env`, `verify`, `compat`, `consist`), as close as
possible to the present values, by optimization (z3). Every value it
returns has passed the check itself.

1. Name the number in the contract: `"constants": {"lam": 4}` and `lam` in
   the term (`b - t <= lam`); in a `.ltl` file, `real constant lam 4;`.
2. Call `repair` with the check that failed and the constants that may
   change, each with a range: `"parameters": {"lam": {"low": 0, "high":
   10}}` (add `"integer": true` for an integer). Give only the constants
   that the user lets change; give the constants of a part rather than
   those of a requirement.
3. Read `status`:
   - `holds`: the present values pass; the check holds and nothing changes
     (repair is then a verification).
   - `repaired`: `values` pass, at the least change (`cost`); `optimal`
     says whether no smaller change exists in the ranges. `check` is the
     result of the check with the values.
   - `impossible`: no values in the ranges pass. Widen a range, let
     another constant change, or change the form of a term (ask the user).
   - `unknown`: with the `reason` (a timeout, a back end missing).
4. Several constants that may change: give them in one call; the cost is
   the sum of the changes. With `minimize` or `maximize` (a term over the
   constants), the cost is that term. To compare repairs (the bound of a
   part, or the requirement), run one repair for each and show both.
5. Propose the values to the user in one sentence, with what they change
   ("Brake 1 may start 4.05 ms after its timestamp, not 4"). A constant of
   a requirement changes only when the user agrees. Then write the value
   in the contract and run the checks that read it.

After a change, run the check that failed again, and the checks of the
parts that read a signal you changed.

Rules:

- Do not make a check pass with `false`, with assumptions that contradict
  each other, or with assumptions on the outputs of the part.
- A requirement that the user gave is changed only when the user agrees.
  A part that the user already has (its behavior or its code) counts as a
  requirement. After a check fails, show the core or the trace, propose
  the change in one sentence, and wait for the answer: do not run the next
  checks on a requirement the user has not accepted.
- Do not add signals between the parts to make a check pass.
- When the same check fails three times after changes, stop. Show the user
  the core and the trace, and ask.

## 6. The end

The loop ends when every contract is verified, every refinement holds on
every level, and every part to synthesize is realizable. Report:

- the tree of the parts, as a diagram (`diagrams.md`);
- each change, with the core or the trace that asked for it;
- what is still unknown, and why (`reason`).

## Files

Keep the contracts in a specification file (`.ltl`). Drawn with
`visualize` (`path`) or `chase-cps view FILE --check`, the results are kept
next to the file (`crossing.ltl` gives `crossing.results.json`), and a
contract that has not changed is not checked again. In the loop, draw again after each change: only the
checks of what changed run.

## 6. Optimization over behaviors

Use `minimize` or `maximize` with an `objective` and a `contract` to find
an expression's extremum over behaviors satisfying both assumptions and
guarantees. Alternatively give `subject_to` formulas and `variables` with
their types. The temporal operators must have finite step intervals.
For a numeric property, `minimize` computes worst-case robustness. A
negative value has a violating witness. `maximize` computes best-case
robustness, so a positive value does not establish that every behavior
satisfies the property. Distinguish these tools from the objective options
of `repair`, which search over parameter values.

Read the result status before using its value: `optimal` means the bound
is reached, `not_attained` is an infimum or supremum, `unbounded` has no
finite bound, and `infeasible` means there is no admissible behavior.
`unknown` provides no optimum. If z3 is missing, install `chase-mcp[z3]`.
