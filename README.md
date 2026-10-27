# CHASE MCP server

This repository contains a [Model Context Protocol][MCP] (MCP) server and an
agent skill for [CHASE][WEB] (Contract-based Heterogeneous Analysis and
Systems Exploration).

The server exposes the contract operations of CHASE as tools that an AI agent
can call: an agent can write assume-guarantee contracts, compose them, check
refinement, and use the counterexamples returned by the model checker to fix
the specification. The skill tells the agent how to use these tools.

## Tools

The tools are in three layers.

**1. Contract algebra.** The operations that build contracts; each tool
returns a new contract. They hold for any assume-guarantee contracts.

- **compose**: parallel composition of two or more contracts; variables with
  the same name are connected. With `discharge`, the result keeps the terms
  of the contracts and drops the assumptions discharged by the other
  contracts (this uses the checks of layer 2).
- **conjoin** and **disjoin**: conjunction and disjunction (greatest lower
  bound and least upper bound).
- **merge**: merging of viewpoints of the same component.
- **divide**: the quotient, i.e. the contract of a missing component.
- **separate**: separation, the adjoint of merging.
- **imply** and **coimply**: implication and coimplication, the adjoints of
  conjunction and disjunction.
- **invert**: the reciprocal (G, A), the contract seen from its environment.
- **assume** and **ensure**: add an assumption or a guarantee.
- **saturate**: the equivalent contract (A, A -> G).
- **simplify**: rewrites the formulas, as the simplify command of
  `logics_tool` (negations moved to the atoms, temporal operators grouped).

**2. Checks.** Each tool returns a status and, when the check fails, a
counterexample. The checks on contracts reduce to queries on formulas, which
nuXmv decides. They take a `context`: formulas that every behavior
satisfies, such as the axiom of an encoding of finite traces.

- **refines**: whether a contract refines another one, and which part fails
  (assumptions or guarantees).
- **verify**: whether the assumptions and the guarantees can hold together
  (A & G satisfiable), which implies compatibility and consistency;
  **is_compatible** (some environment satisfies the assumptions) and
  **is_consistent** (some behavior satisfies the contract) check them one at
  a time.
- **implements** and **accepts**: whether an implementation satisfies the
  contract, and whether the contract accepts an environment, given as LTL
  formulas or as state machines (an SMV model, a state machine in JSON, or a
  controller from `synthesize`).
- **is_receptive**: whether a state machine accepts every input that the
  assumptions allow, with the state and the input it refuses.
- **remove_redundant**: removes the assumptions and guarantees implied by the
  other terms of the contract.
- **implies** and **is_satisfiable**, on formulas: validity of an
  implication, and satisfiability of a formula (some behavior satisfies it;
  this is not the satisfaction of a contract by a component, which is
  `implements`).
- **unsat_core**: a minimal set of terms that cannot hold together;
  `verify`, `is_compatible`, `is_consistent`, and `is_satisfiable` return
  it with `core`.

**3. GR(1) synthesis, with slugs.** These tools are about synthesizing a
component from a contract in the GR(1) fragment of LTL, not about contracts
in general.

- **is_realizable**: GR(1) realizability, with the counter-strategy of the
  environment when unrealizable; **synthesize** also builds the controller.
- **unrealizable_core**: a minimal set of guarantees that is unrealizable;
  `is_realizable` returns it with `core`.
- **is_well_separated**: whether the component can win by forcing the
  environment to violate its assumptions while it keeps its safety
  guarantees, with that strategy and the assumptions that cause it.
- **is_vacuous**: whether the component can win without an output that a
  liveness guarantee asks for (vacuity in synthesis), with that strategy and
  the assumptions that allow it.
- **remove_vacuous**: removes the terms that are redundant in the GR(1) game,
  keeping realizability and the controllers (where `remove_redundant` keeps
  A -> G).

Specifications:

- **read_spec** and **write_spec**: read and write contracts in the logics
  language of CHASE (the `.ltl` files of `logics_tool`).

A contract is given in JSON:

```json
{"name": "Arbiter",
 "inputs": {"req": "bool", "n": [0, 3]},
 "outputs": {"grant": "bool"},
 "assumptions": ["G F !req"],
 "guarantees": ["G (req -> F grant)"]}
```

Variables are Boolean (`"bool"`), bounded integers (`[low, high]`), or reals
(`"real"`). Formulas use the standard LTL syntax: `! & | -> <-> G F X U R W`,
relations, arithmetic, numbers such as `20.5`, and `x'` for the value of `x`
in the next step.

## Requirements

- The CHASE Python package, `chase-cps`, installed with the server.
- [nuXmv][NUXMV] for the checks (free for academic and non-commercial use),
  in the `PATH` or given with the environment variable `CHASE_NUXMV`;
  [NuSMV][NUSMV] where nuXmv cannot be used.
- [slugs][SLUGS] for the realizability checks.

`chase-cps install nuxmv --accept-license` and `chase-cps install slugs`
install them, and `chase-cps doctor` shows the tools found.
The [CHASE Docker image][CHASE] contains all of them.

## Installation

The server is a Python program that runs on the standard input and output.
With [uv][UV] there is nothing to install: `uvx chase-mcp` downloads and runs
it. Otherwise:

`$> pip install chase-mcp`

and use `chase-mcp` in place of `uvx chase-mcp` below.

The development version is installed from the repositories:

`$> pip install "chase-cps @ git+https://github.com/chase-cps/chase" "chase-mcp @ git+https://github.com/chase-cps/chase-mcp"`

### Claude Code

The server and the skill are packaged as a plugin:

```
/plugin marketplace add chase-cps/chase-mcp
/plugin install chase@chase-cps
```

Or only the server:

`$> claude mcp add chase -- uvx chase-mcp`

### Codex

`$> codex mcp add chase -- uvx chase-mcp`

or, in `~/.codex/config.toml`:

```toml
[mcp_servers.chase]
command = "uvx"
args = ["chase-mcp"]
```

### Cursor, Claude Desktop, Gemini CLI, and other clients

Most MCP clients read the same JSON configuration. Add the server to the
`mcpServers` object of the configuration file (`.cursor/mcp.json` or
`~/.cursor/mcp.json` for Cursor, `claude_desktop_config.json` for Claude
Desktop, `~/.gemini/settings.json` for Gemini CLI):

```json
{"mcpServers": {"chase": {"command": "uvx", "args": ["chase-mcp"]}}}
```

VS Code uses `servers` in `.vscode/mcp.json`:

```json
{"servers": {"chase": {"type": "stdio", "command": "uvx", "args": ["chase-mcp"]}}}
```

OpenCode uses `mcp` in `opencode.json`:

```json
{"mcp": {"chase": {"type": "local", "command": ["uvx", "chase-mcp"]}}}
```

To set the model checker, add `"env": {"CHASE_NUXMV": "/path/to/nuXmv"}` to
the server entry (`environment` in OpenCode, `env = { ... }` in Codex).

## Skill

The skill is in `skills/chase-contracts`. It follows the [Agent Skills][SKILLS]
format (a `SKILL.md` file with instructions), and it also works without the
MCP server: the agent then uses the `chase_cps` Python package. The
`examples` folder of the skill contains complete examples; each one is run by
the tests, so the results they state are the ones CHASE returns.

- Claude Code: installed with the plugin, or copy the folder to
  `~/.claude/skills/`.
- Codex: copy the folder to `~/.agents/skills/` (or `.agents/skills/` in a
  project).
- Other agents that support Agent Skills: copy the folder to their skills
  directory.

## Testing

`$> pip install ".[test]"`

`$> pytest`

The tests need nuXmv (`chase-cps install nuxmv --accept-license`).

## License

This project is released under the 3-Clause BSD License.

[MCP]: https://modelcontextprotocol.io
[WEB]: https://chase-cps.github.io
[CHASE]: https://github.com/chase-cps/chase
[NUXMV]: https://nuxmv.fbk.eu/
[NUSMV]: https://nusmv.fbk.eu/
[SLUGS]: https://github.com/VerifiableRobotics/slugs
[UV]: https://docs.astral.sh/uv/
[SKILLS]: https://agentskills.io
