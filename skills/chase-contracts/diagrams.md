# Diagrams

Draw when a picture helps the user more than text: a decomposition (the
parts inside the contract they should refine), a quotient (the missing part
as a dashed box, with a candidate inside), a check that fails (its core in
red), or a state machine against its contract. Do not draw for a single
contract with a single result: say it in words.

The contracts are put together by their ports, so that a specification
written for the user is drawn as the design, with nothing more to say:

- An output and an input with the same name are wired. Give a signal the
  same name in the contract that drives it and in the contracts that read
  it.
- Contracts with the same inputs and outputs are versions of one part (a
  fix, a candidate). The first one in the file is wired; the others are
  drawn apart.
- A contract whose outputs several parts drive, and which gives them what
  they read from outside, is the contract of their composition: the parts
  are drawn inside it, and the refinement is checked (⪯, green or red).
  Write the contract of the system with the inputs and outputs it has from
  the outside, and the signals between the parts as outputs of the parts
  only.
- While a part is not written yet (two parts or more are, and some outputs
  of the system are driven by none), it is drawn as a hole: the quotient
  of the system by the parts, with the ports the missing part must have.

How to draw:

- With the MCP server: `visualize`, with the contracts as JSON
  (`contracts`), a specification (`text`), or a file (`path`). `check` (the
  default) checks A∧G of each contract (with the core when it fails) and
  the refinements drawn. For a file, the results are kept next to it
  (`FILE.results.json`): the user sees them in the editor, and a contract
  that has not changed is not checked again. `draw` and `refines` give another
  arrangement: `draw: ["A+B"]` draws the composition of A and B,
  `refines: [[refined, abstract]]` draws the refined one inside.
- In a shell, without the server: write the contracts to a `.ltl` file and
  run `chase-cps view FILE.ltl --check`, which writes `FILE.html`. With the
  CHASE extension of VS Code, the user sees the diagram beside the file,
  drawn again as they type, and checked on save.
- `verify` and `realizable` (`--verify`, `--realizable`) check each
  contract drawn; a failure marks its core. `open` names the contracts
  drawn open: open the ones whose terms or core the user should read now,
  and leave the others closed, so that the page stays readable.
- The tool runs the checks it is asked for: results of other tool calls are
  not carried over. Ask only for the checks you will talk about.
- Give the user the path of the page (it opens in any browser) and say in
  one or two sentences what to look at: which box, which tag, which red
  terms. The page can export the diagram as SVG, PNG, or PDF.
