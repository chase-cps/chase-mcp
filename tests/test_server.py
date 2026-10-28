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
    assert {"compose", "conjoin", "disjoin", "merge", "divide", "separate", "saturate",
            "simplify", "refines", "verify", "is_consistent", "is_compatible",
            "is_realizable", "synthesize", "implies", "is_satisfiable", "implements",
            "accepts", "remove_redundant", "read_spec", "write_spec", "imply", "coimply",
            "invert", "assume", "ensure", "unsat_core", "unrealizable_core", "is_well_separated",
            "is_vacuous", "is_receptive"} == asyncio.run(run())


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
    err, terms = call("compose", {"contracts": [c1, c2], "discharge": True})
    assert not err and terms["assumptions"] == ["G a"]
    err, r = call("refines", {"refined": terms, "abstract": top})
    assert not err and r["status"] == "valid"


def test_consistency_compatibility_and_implies():
    err, r = call("is_consistent", {"contract": SPEC})
    assert not err and r["status"] == "sat"
    err, r = call("verify", {"contract": SPEC})
    assert not err and r["status"] == "sat" and r["compatible"]["status"] == "sat"
    contradictory = dict(SPEC, assumptions=["G req", "F !req"])
    err, r = call("is_compatible", {"contract": contradictory})
    assert not err and r["status"] == "unsat"
    err, r = call("implies", {"phi": "G (req -> F grant)", "psi": "G (req -> X grant)",
                              "variables": {"req": "bool", "grant": "bool"}})
    assert not err and r["status"] == "invalid" and "trace" in r


def test_errors_are_reported_not_fatal():
    bad = dict(SPEC, guarantees=["G (req -> F"])
    err, text = call("refines", {"refined": bad, "abstract": SPEC})
    assert err and "syntax error" in text
    # The server is still usable after an error.
    err, r = call("is_compatible", {"contract": SPEC})
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


def test_server_version():
    import chase_mcp

    async def run():
        async with Client(server) as client:
            return client.server_info
    info = asyncio.run(run())
    assert info.name == "chase" and info.version == chase_mcp.__version__


def test_context():
    # Finite traces encoded with alive: without the axiom, the words where
    # alive is false from the start satisfy both guarantees.
    c = {"name": "C", "inputs": {"alive": "bool"}, "outputs": {"a": "bool"},
         "guarantees": ["G (alive -> a)", "G (alive -> !a)"]}
    err, r = call("verify", {"contract": c})
    assert not err and r["status"] == "sat"
    err, r = call("verify", {"contract": c, "context": ["alive & (alive U G !alive)"]})
    assert not err and r["status"] == "unsat"
    err, r = call("verify", {"contract": c, "context": ["G x"]})
    assert err and "undeclared variables ['x'] in the context" in r


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
    err, q = call("divide", {"system": system, "part": part})
    assert not err and "b" in q["outputs"]
    err, comp = call("compose", {"contracts": [part, q]})
    assert not err
    assert call("refines", {"refined": comp, "abstract": system})[1]["status"] == "valid"


def test_implementation_and_environment():
    err, r = call("implements",
                  {"implementation": "G (req -> X grant)", "contract": SPEC})
    assert not err and r["status"] == "valid"
    err, r = call("accepts", {"contract": SPEC, "environment": "G req"})
    assert not err and r["status"] == "invalid"


BLOCKING = """MODULE main
IVAR
  req : boolean;
VAR
  grant : boolean;
ASSIGN
  init(grant) := FALSE;
TRANS
  next(grant) = req
TRANS
  !(grant & req)
"""
NEXT = {"name": "Next", "inputs": {"req": "bool"}, "outputs": {"grant": "bool"},
        "guarantees": ["G (req -> X grant)"]}


def test_state_machines():
    err, r = call("implements", {"contract": NEXT, "smv": BLOCKING})
    assert not err and r["status"] == "valid"
    err, r = call("is_receptive", {"contract": NEXT, "smv": BLOCKING})
    assert not err and r["status"] == "not_receptive"
    assert r["details"]["input"] == {"req": True}
    machine = {"name": "Slow", "inputs": {"req": "bool"}, "outputs": {"grant": "bool"},
               "states": ["idle", "busy"], "initial": "idle",
               "transitions": [
                   {"from": "idle", "when": "req", "outputs": {"grant": False}, "to": "busy"},
                   {"from": "idle", "when": "!req", "outputs": {"grant": False}, "to": "idle"},
                   {"from": "busy", "outputs": {"grant": True}, "to": "idle"}]}
    err, r = call("implements", {"contract": NEXT, "machine": machine})
    assert not err and r["status"] == "invalid"
    err, r = call("is_receptive", {"contract": NEXT, "machine": machine})
    assert not err and r["status"] == "receptive"
    env = "MODULE main\nVAR\n  req : boolean;\nASSIGN\n  init(req) := FALSE;\n  next(req) := !req;\n"
    spaced = {**NEXT, "name": "Spaced", "assumptions": ["G (req -> X !req)"]}
    err, r = call("accepts", {"contract": spaced, "smv": env})
    assert not err and r["status"] == "valid"
    err, msg = call("implements", {"contract": NEXT})
    assert err and "formula or as a state machine" in msg
    err, msg = call("implements", {"contract": NEXT, "smv": "MODULE main\nVAR\n  x : boolean;\n"})
    assert err and "does not declare" in msg


slugs = pytest.mark.skipif(not ADAPTERS["slugs"].available(), reason="slugs not installed")


@slugs
def test_controller_and_vacuity():
    arb = {"name": "Arb", "inputs": {"req": "bool"}, "outputs": {"grant": "bool"},
           "assumptions": ["!req", "G ((req & grant) -> X !req)", "G ((req & !grant) -> X req)"],
           "guarantees": ["!grant", "G (grant -> req)", "G F (!req | grant)"]}
    err, r = call("synthesize", {"contract": arb})
    assert not err and r["status"] == "realizable"
    err, q = call("implements", {"contract": arb, "controller": r["controller"]})
    assert not err and q["status"] == "valid"
    err, q = call("is_receptive", {"contract": arb, "controller": r["controller"]})
    assert not err and q["status"] == "receptive"
    free = {**arb, "name": "Free", "assumptions": []}
    err, q = call("is_receptive", {"contract": free, "controller": r["controller"],
                                   "synthesized_from": arb})
    assert not err and q["status"] == "not_receptive"
    err, v = call("is_vacuous", {"contract": arb})
    assert not err and v["status"] == "not_vacuous" and v["checked"] == ["grant"]
    trusting = {**arb, "name": "Trusting", "assumptions": ["!req", "G F !req"]}
    err, v = call("is_vacuous", {"contract": trusting, "core": True})
    assert not err and v["status"] == "vacuous"
    assert v["vacuous"][0]["mode"] == "never" and v["vacuous"][0]["core"]["core"] == ["G F !req"]


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


def test_implication_reciprocal_and_actions():
    err, i = call("imply", {"premise": SPEC, "conclusion": IMPL})
    assert not err
    err, meet = call("conjoin", {"contracts": [i, SPEC]})
    assert call("refines", {"refined": meet, "abstract": IMPL})[1]["status"] == "valid"
    err, k = call("coimply", {"first": SPEC, "second": IMPL})
    assert not err and k["name"]
    err, r = call("invert", {"contract": SPEC})
    assert not err and set(r["inputs"]) == {"grant"} and set(r["outputs"]) == {"req"}
    err, a = call("assume", {"contract": SPEC, "formula": "G F grant"})
    assert call("refines", {"refined": SPEC, "abstract": a})[1]["status"] == "valid"
    err, e = call("ensure", {"contract": SPEC, "formula": "G (grant -> X !grant)"})
    assert call("refines", {"refined": e, "abstract": SPEC})[1]["status"] == "valid"
    err, msg = call("assume", {"contract": SPEC, "formula": "G z"})
    assert err and "undeclared" in msg


def test_cores():
    arb = {"name": "Arb", "inputs": {"req": "bool", "stop": "bool"}, "outputs": {"grant": "bool"},
           "assumptions": ["G F req"],
           "guarantees": ["!grant", "G (req -> X grant)", "G (stop -> X !grant)", "G F grant"]}
    if ADAPTERS["slugs"].available():
        err, r = call("unrealizable_core", {"contract": arb})
        assert not err and r["status"] == "found"
        assert r["core"]["guarantees"] == ["G (req -> X grant)", "G (stop -> X !grant)"]
        err, r = call("is_realizable", {"contract": arb, "core": True})
        assert not err and r["core"]["status"] == "found"
    err, r = call("unsat_core", {"formulas": ["p", "G (p -> X p)", "G F q", "F !p"],
                                 "variables": {"p": "bool", "q": "bool"}})
    assert not err and r["core"] == ["p", "G (p -> X p)", "F !p"]
    c = {"name": "C", "inputs": {"a": "bool"}, "outputs": {"b": "bool"},
         "assumptions": ["G a", "F !a"], "guarantees": ["G b"]}
    err, r = call("is_compatible", {"contract": c, "core": True})
    assert not err and r["status"] == "unsat" and r["core"]["core"]["assumptions"] == ["G a", "F !a"]
    err, msg = call("unsat_core", {})
    assert err and "either" in msg


@pytest.mark.skipif(not ADAPTERS["slugs"].available(), reason="slugs not installed")
def test_well_separation():
    c = {"name": "Arb", "inputs": {"req": "bool"}, "outputs": {"grant": "bool"},
         "assumptions": ["G F req", "G (grant -> X !req)"], "guarantees": ["G !grant"]}
    # without the guarantees (Def. 2), granting forever forces the violation
    err, r = call("is_well_separated", {"contract": c, "core": True, "with_guarantees": False})
    assert not err and r["status"] == "not_separated" and "controller" in r
    assert r["core"]["core"]["assumptions"] == ["G F req", "G (grant -> X !req)"]
    # keeping G !grant (the default), the component cannot
    err, r = call("is_well_separated", {"contract": c})
    assert not err and r["status"] == "separated"


def test_remove_redundant_for_synthesis():
    c = {"name": "A", "inputs": {"req": "bool"}, "outputs": {"grant": "bool"},
         "assumptions": ["G F req"], "guarantees": ["G (req -> grant)", "G F grant"]}
    err, r = call("remove_redundant", {"contract": c, "synth": True, "core": True})
    assert not err and r["contract"]["guarantees"] == ["G (req -> grant)"]
    assert r["removed"] == [{"term": "G F grant", "part": "guarantee", "kind": "justice",
                             "core": ["G F req", "G (req -> grant)"]}]
    # the two differ when the assumptions are wrong
    bad = {"name": "Bad", "inputs": {"x": "bool"}, "outputs": {"g": "bool"},
           "assumptions": ["G F (x & !x)"], "guarantees": ["G g", "G !g"]}
    err, r = call("remove_redundant", {"contract": bad})
    assert not err and r["contract"]["guarantees"] == []
    err, r = call("remove_redundant", {"contract": bad, "synth": True})
    assert not err and r["contract"]["guarantees"] == ["G g", "G !g"]
    err, r = call("remove_redundant", {"contract": c, "synth": True, "context": ["G req"]})
    assert err


def test_real_variables():
    mode = {"name": "Mode", "inputs": {"kias": "real"}, "outputs": {"wing": "bool"},
            "guarantees": ["G (kias > 40 -> X wing)", "G (kias <= 30.5 -> X !wing)"]}
    spec = {"name": "Spec", "inputs": {"kias": "real"}, "outputs": {"wing": "bool"},
            "guarantees": ["G (kias > 45 -> X wing)"]}
    err, r = call("refines", {"refined": mode, "abstract": spec})
    assert not err and (r["status"], r["reals"]) == ("valid", "regions")
    err, r = call("refines", {"refined": spec, "abstract": mode})
    assert not err and r["status"] == "invalid"
    trace = r["guarantees"]["trace"]
    assert all(isinstance(s["kias"], (int, float, str)) for s in trace["prefix"] + trace["loop"])
