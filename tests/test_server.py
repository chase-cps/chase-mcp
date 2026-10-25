"""Tests of the chase-mcp tools, through an MCP client."""

import asyncio
import json
import os
import shutil
import sys

import pytest
from mcp import Client, StdioServerParameters

from chase_mcp.server import server

pytestmark = pytest.mark.skipif(
    not (shutil.which("nuXmv") or shutil.which("NuSMV")),
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
            return result.is_error, (text if result.is_error else json.loads(text))
    return asyncio.run(run())


def test_tools_are_listed():
    async def run():
        async with Client(server) as client:
            return {t.name for t in (await client.list_tools()).tools}
    assert {"compose", "refine", "check", "quotient", "separation", "implies",
            "remove_redundant"} <= asyncio.run(run())


def test_refine_valid_and_counterexample():
    err, r = call("refine", {"refined": IMPL, "abstract": SPEC})
    assert not err and r["status"] == "valid"
    err, r = call("refine", {"refined": SPEC, "abstract": IMPL})
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
    err, r = call("refine", {"refined": comp, "abstract": top})
    assert not err and r["status"] == "valid"


def test_check_and_implies():
    err, r = call("check", {"contract": SPEC})
    assert not err and r["consistent"]["status"] == "sat"
    err, r = call("implies", {"phi": "G (req -> F grant)", "psi": "G (req -> X grant)",
                              "variables": {"req": "bool", "grant": "bool"}})
    assert not err and r["status"] == "invalid" and "trace" in r


def test_errors_are_reported_not_fatal():
    bad = dict(SPEC, guarantees=["G (req -> F"])
    err, text = call("refine", {"refined": bad, "abstract": SPEC})
    assert err and "syntax error" in text
    # The server is still usable after an error.
    err, r = call("check", {"contract": SPEC, "properties": ["compatible"]})
    assert not err and r["compatible"]["status"] == "sat"


def test_stdio_server():
    params = StdioServerParameters(command=sys.executable, args=["-m", "chase_mcp"],
                                    env=dict(os.environ))
    err, r = call("refine", {"refined": IMPL, "abstract": SPEC}, target=params)
    assert not err and r["status"] == "valid"
