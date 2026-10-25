"""Tests of the chase-mcp tools, through an MCP client."""

import asyncio
import json
import os
import sys

import pytest
from chase_cps.backends import ADAPTERS
from mcp import Client, StdioServerParameters

from chase_mcp.server import server

pytestmark = pytest.mark.skipif(
    not (ADAPTERS["nuxmv"].available() or ADAPTERS["nusmv"].available()),
    reason="nuXmv/NuSMV not installed")

SPEC = {"name": "Spec", "inputs": {"req": "bool"}, "outputs": {"grant": "bool"},
        "assumptions": ["G F !req"], "guarantees": ["G (req -> F grant)"]}
IMPL = {"name": "Impl", "inputs": {"req": "bool"}, "outputs": {"grant": "bool"},
        "guarantees": ["G (req -> X grant)"]}


def call(name, arguments, target=server):
    async def run():
        async with Client(target) as client:
            result = await client.call_tool(name, arguments)
            text = result.content[0].text
            if result.is_error:
                return True, text
            try:
                return False, json.loads(text)
            except json.JSONDecodeError:
                return False, text
    return asyncio.run(run())


def test_tools_are_listed():
    async def run():
        async with Client(server) as client:
            return {t.name for t in (await client.list_tools()).tools}
    assert {"compose", "conjoin", "disjoin", "merge", "quotient", "separation",
            "refines", "consistent", "compatible", "realizable", "implies",
            "satisfiable", "contains_environment", "contains_implementation",
            "saturate", "simplify", "remove_redundant", "read_spec",
            "write_spec"} == asyncio.run(run())


def test_refine_valid_and_counterexample():
    err, r = call("refines", {"refined": IMPL, "abstract": SPEC})
    assert not err and r["status"] == "valid"
    err, r = call("refines", {"refined": SPEC, "abstract": IMPL})
    assert not err and r["status"] == "invalid" and r["failed"] == "assumptions"
    assert r["assumptions"]["trace"]["loop"]


def test_compose_then_refine():
    c1 = {"name": "C1", "inputs": {"a": "bool"}, "outputs": {"b": "bool"},
          "assumptions": ["G a"], "guarantees": ["G (a -> b)"]}
    c2 = {"name": "C2", "inputs": {"b": "bool"}, "outputs": {"c": "bool"},
          "assumptions": ["G b"], "guarantees": ["G (b -> c)"]}
    top = {"name": "Top", "inputs": {"a": "bool"}, "outputs": {"c": "bool"},
           "assumptions": ["G a"], "guarantees": ["G c"]}
    err, comp = call("compose", {"contracts": [c1, c2], "name": "Sys"})
    assert not err and comp["name"] == "Sys" and "b" in comp["outputs"]
    err, r = call("refines", {"refined": comp, "abstract": top})
    assert not err and r["status"] == "valid"


def test_consistency_compatibility_and_implies():
    err, r = call("consistent", {"contract": SPEC})
    assert not err and r["status"] == "sat"
    contradictory = dict(SPEC, assumptions=["G req", "F !req"])
    err, r = call("compatible", {"contract": contradictory})
    assert not err and r["status"] == "unsat"
    err, r = call("implies", {"phi": "G (req -> F grant)", "psi": "G (req -> X grant)",
                              "variables": {"req": "bool", "grant": "bool"}})
    assert not err and r["status"] == "invalid" and "trace" in r


def test_errors_are_reported_not_fatal():
    bad = dict(SPEC, guarantees=["G (req -> F"])
    err, text = call("refines", {"refined": bad, "abstract": SPEC})
    assert err and "syntax error" in text
    # The server is still usable after an error.
    err, r = call("compatible", {"contract": SPEC})
    assert not err and r["status"] == "sat"


def test_stdio_server():
    params = StdioServerParameters(command=sys.executable, args=["-m", "chase_mcp"],
                                    env=dict(os.environ))
    err, r = call("refines", {"refined": IMPL, "abstract": SPEC}, target=params)
    assert not err and r["status"] == "valid"
    # The CHASE libraries print messages while parsing: they must not reach
    # the standard output, which carries the protocol.
    err, r = call("compose", {"contracts": [SPEC, dict(IMPL, name="Impl2",
                                                       outputs={"ack": "bool"},
                                                       guarantees=["G ack"])]},
                  target=params)
    assert not err and r["name"]


def test_algebra_bounds():
    err, meet = call("conjoin", {"contracts": [SPEC, IMPL]})
    assert not err
    err, join = call("disjoin", {"contracts": [SPEC, IMPL]})
    assert not err
    for c in (SPEC, IMPL):
        assert call("refines", {"refined": meet, "abstract": c})[1]["status"] == "valid"
        assert call("refines", {"refined": c, "abstract": join})[1]["status"] == "valid"


def test_quotient_with_part_refines_system():
    system = {"name": "Sys", "inputs": {"a": "bool"}, "outputs": {"c": "bool"},
              "assumptions": ["G a"], "guarantees": ["G c"]}
    part = {"name": "Part", "inputs": {"b": "bool"}, "outputs": {"c": "bool"},
            "assumptions": ["G b"], "guarantees": ["G (b -> c)"]}
    err, q = call("quotient", {"system": system, "part": part})
    assert not err and "b" in q["outputs"]
    err, comp = call("compose", {"contracts": [part, q]})
    assert not err
    assert call("refines", {"refined": comp, "abstract": system})[1]["status"] == "valid"


def test_implementation_and_environment():
    err, r = call("contains_implementation",
                  {"contract": SPEC, "implementation": "G (req -> X grant)"})
    assert not err and r["status"] == "valid"
    err, r = call("contains_environment", {"contract": SPEC, "environment": "G req"})
    assert not err and r["status"] == "invalid"


def test_spec_round_trip():
    err, text = call("write_spec", {"contracts": [SPEC], "name": "demo"})
    assert not err and "CONTRACT Spec" in text
    err, r = call("read_spec", {"text": text})
    assert not err and r["contracts"][0]["name"] == "Spec"
    err, msg = call("read_spec", {"path": "/nonexistent.ltl"})
    assert err and "no such file" in msg



def test_native_output_does_not_reach_protocol():
    import subprocess
    code = ("import os; from chase_mcp.server import _protocol_stdout; "
            "out = _protocol_stdout(); os.write(1, b'INFO: native\\n'); "
            "out.write('protocol\\n'); out.flush()")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=60, env=dict(os.environ))
    assert p.stdout == "protocol\n"
    assert "INFO: native" in p.stderr


def test_saturate_simplify_and_remove_redundant():
    err, s = call("saturate", {"contract": SPEC})
    assert not err and s["guarantees"] == ["G F !req -> G (req -> F grant)"]
    redundant = dict(SPEC, assumptions=["G F !req", "F !req"],
                     guarantees=["G (req -> X grant)", "G (req -> F grant)"])
    err, s = call("simplify", {"contract": dict(SPEC, guarantees=["F grant | F req"])})
    assert not err and s["guarantees"] == ["F (grant | req)"]
    err, r = call("remove_redundant", {"contract": redundant})
    assert not err
    assert r["removed_assumptions"] == ["F !req"]
    assert r["removed_guarantees"] == ["G (req -> F grant)"]
    assert r["contract"]["guarantees"] == ["G (req -> X grant)"]
