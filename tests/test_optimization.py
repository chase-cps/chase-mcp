"""Optimization through the MCP client, including non-optimal outcomes."""
import pytest

from test_server import call


@pytest.mark.parametrize("tool, expected", [("minimize", 2), ("maximize", 5)])
def test_expression_over_contract(tool, expected):
    pytest.importorskip("z3")
    error, result = call(tool, {
        "objective": "x", "contract": {"outputs": {"x": [0, 9]},
        "guarantees": ["x >= 2", "x <= 5"]}})
    assert not error, result
    assert result["status"] == "optimal" and result["value"] == expected
    assert result["values"]["x"] == expected


@pytest.mark.parametrize("tool, expected", [("minimize", -2), ("maximize", 3)])
def test_property_robustness_and_witness(tool, expected):
    pytest.importorskip("z3")
    from chase_cps import Trace
    from chase_cps.robustness import robustness
    error, result = call(tool, {"objective": "G[0,2] (x <= 3)",
        "subject_to": ["G[0,2] (x >= 0)", "G[0,2] (x <= 5)"],
        "variables": {"x": "real"}})
    assert not error, result
    assert result["status"] == "optimal" and result["value"] == expected
    trace = Trace(**result["trace"])
    assert robustness("G[0,2] (x <= 3)", trace) == expected


@pytest.mark.parametrize("tool, constraints, status", [
    ("minimize", "x > 1", "not_attained"),
    ("maximize", "x > 1", "unbounded"),
    ("minimize", "x > 1 & x < 0", "infeasible"),
    ("minimize", "G (x > 1)", "unknown"),
])
def test_non_optimal_statuses(tool, constraints, status):
    pytest.importorskip("z3")
    error, result = call(tool, {"objective": "x", "subject_to": constraints,
                               "variables": {"x": "real"}})
    assert not error, result
    assert result["status"] == status
    if status == "not_attained":
        assert result["value"] == 1
    if status == "unknown":
        assert "bounded" in result["reason"]


@pytest.mark.parametrize("tool", ["minimize", "maximize"])
def test_invalid_constraint_sources(tool):
    error, result = call(tool, {"objective": "x"})
    assert error and "exactly one" in result
    error, result = call(tool, {"objective": "x", "contract": {}, "subject_to": "true"})
    assert error and "exactly one" in result
    error, result = call(tool, {"objective": "G (", "subject_to": "true"})
    assert error and "syntax error" in result


def test_missing_z3_is_unknown(monkeypatch):
    from chase_cps.backends import z3
    monkeypatch.setattr(z3, "_z3", None)
    error, result = call("minimize", {"objective": "x", "subject_to": "x >= 0",
                                     "variables": {"x": "real"}})
    assert not error and result["status"] == "unknown"
    assert "z3" in result["reason"]
