# CHASE MCP server

This repository contains a [Model Context Protocol][MCP] (MCP) server for
[CHASE][WEB] (Contract-based Heterogeneous Analysis and Systems Exploration).
The server exposes the contract operations of CHASE as tools that an AI agent
can call: an agent can write assume-guarantee contracts, compose them, check
refinement, and use the counterexamples returned by the model checker to fix
the specification.

## Tools

- **compose**: parallel composition of two or more contracts; variables with
  the same name are connected.
- **quotient** and **separation**: the contract of a missing component.
- **refine**: checks whether a contract refines another one. When it does not,
  the result says which part fails (assumptions or guarantees) and gives a
  counterexample trace.
- **check**: consistency, compatibility, and GR(1) realizability of a contract
  (with the controller, or the counter-strategy of the environment).
- **implies**: validity of an implication between two LTL formulas.
- **remove_redundant**: removes the assumptions and guarantees implied by the
  other terms of the contract.

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

- The CHASE Python package (`chase_cps`), provided by the
  [chase][CHASE] repository.
- A model checker for the checks: [nuXmv][NUXMV] or [NuSMV][NUSMV].
- [slugs][SLUGS] for the realizability checks.

The [CHASE Docker image][CHASE] contains all of them.

## Installation

`$> pip install .`

The server runs on the standard input and output:

`$> chase-mcp`

For instance, to use it from Claude Code:

`$> claude mcp add chase -- chase-mcp`

Or, in the configuration file of an MCP client:

```json
{"mcpServers": {"chase": {"command": "chase-mcp"}}}
```

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
