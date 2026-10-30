"""Runs the examples of the skill through the MCP tools and checks the
results they state."""

import glob
import json
import os

import pytest
from chase_cps.tools import find

from test_server import call, pytestmark  # noqa: F401 (skip without a model checker)

EXAMPLES = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "skills",
                                         "chase-contracts", "examples", "*.json")))


def resolve(value, env):
    if isinstance(value, str) and value.startswith("$"):
        return env[value[1:]]
    if isinstance(value, list):
        return [resolve(v, env) for v in value]
    if isinstance(value, dict):
        return {k: resolve(v, env) for k, v in value.items()}
    return value


@pytest.mark.parametrize("path", EXAMPLES, ids=os.path.basename)
def test_example(path):
    with open(path) as f:
        example = json.load(f)
    env = dict(example.get("contracts", {}))
    if "spec" in example:
        env["spec"] = example["spec"]
    for step in example["steps"]:
        if step.get("needs") and not find(step["needs"]):
            continue
        err, result = call(step["tool"], resolve(step["args"], env))
        assert not err, f'{step["tool"]}: {result}'
        for key, value in step.get("expect", {}).items():
            assert _same(result[key], value), f'{step["tool"]}: {key} is {result[key]!r}'
        if "save" in step:
            env[step["save"]] = result
        if step.get("save_contracts"):
            env.update({c["name"]: c for c in result["contracts"]})


def _same(got, want) -> bool:
    """Equal, with formulas compared as formulas: the printing of a formula
    (its parentheses) may differ between versions of chase-cps."""
    from chase_cps import ltl
    if isinstance(got, list) and isinstance(want, list):
        return len(got) == len(want) and all(_same(g, w) for g, w in zip(got, want))
    if isinstance(got, str) and isinstance(want, str) and got != want:
        try:
            return ltl.parse(got) == ltl.parse(want)
        except Exception:
            return False
    return got == want
