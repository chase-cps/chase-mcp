# CHASE MCP server

This repository contains a [Model Context Protocol][MCP] (MCP) server and an
agent skill for [CHASE][WEB] (Contract-based Heterogeneous Analysis and
Systems Exploration).

The server exposes the contract operations of CHASE as tools that an AI agent
can call: an agent can write assume-guarantee contracts, compose them, check
refinement, and use the counterexamples returned by the model checker to fix
the specification. The skill tells the agent how to use these tools.

## Tools

Contract algebra (each tool returns a new contract):

- **compose**: parallel composition of two or more contracts; variables with
  the same name are connected.
- **conjoin** and **disjoin**: greatest lower bound and least upper bound.
- **merge**: merging of viewpoints of the same component.
- **quotient**: the contract of a missing component.
- **separation**: the adjoint of merging.

Checks (each tool returns a status and, when it fails, a counterexample
trace):

- **refines**: whether a contract refines another one, and which part fails
  (assumptions or guarantees).
- **consistent**: whether some behavior satisfies the contract.
- **compatible**: whether some environment satisfies the assumptions.
- **realizable**: GR(1) realizability, with the controller or the
  counter-strategy of the environment.
- **implies** and **satisfiable**: validity of an implication and
  satisfiability of an LTL formula.
- **contains_environment** and **contains_implementation**: whether an
  environment or an implementation, given as LTL formulas, is accepted by the
  contract.
- **remove_redundant**: removes the assumptions and guarantees implied by the
  other terms of the contract.

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

Variables are Boolean (`"bool"`) or bounded integers (`[low, high]`). Formulas
use the standard LTL syntax: `! & | -> <-> G F X U R W`, relations, arithmetic,
and `x'` for the value of `x` in the next step.

## Requirements

- The CHASE Python package, `chase-cps`, installed with the server.
- A model checker for the checks: [nuXmv][NUXMV] (preferred) or
  [NuSMV][NUSMV], in the `PATH` or given with the environment variables
  `CHASE_NUXMV` and `CHASE_NUSMV`.
- [slugs][SLUGS] for the realizability checks.

The [CHASE Docker image][CHASE] contains all of them.

## Installation

The server is a Python program that runs on the standard input and output.
With [uv][UV] there is nothing to install: `uvx chase-mcp` downloads and runs
it. Otherwise:

`$> pip install chase-mcp`

and use `chase-mcp` in place of `uvx chase-mcp` below.

Until the first release on PyPI, install from the repositories:

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
format (a `SKILL.md` file with instructions and examples), and it also works
without the MCP server: the agent then uses the `chase_cps` Python package.

- Claude Code: installed with the plugin, or copy the folder to
  `~/.claude/skills/`.
- Codex: copy the folder to `~/.agents/skills/` (or `.agents/skills/` in a
  project).
- Other agents that support Agent Skills: copy the folder to their skills
  directory.

## Testing

`$> pip install ".[test]"`

`$> pytest`

The tests need nuXmv or NuSMV in the `PATH`.

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
