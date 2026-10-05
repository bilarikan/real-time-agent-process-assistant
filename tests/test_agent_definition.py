from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.sales_agent.okf_search_index import OKFError


def _load_agent_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("LIVE_MODEL_ID", "test-live-model")
    sys.modules.pop("app.sales_agent.agent", None)
    return importlib.import_module("app.sales_agent.agent")


def test_agent_registers_only_local_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_agent_module(monkeypatch)

    names = {
        getattr(tool, "__name__", getattr(tool, "name", "")) for tool in module.root_agent.tools
    }

    assert module.root_agent.model == "test-live-model"
    assert names == {
        "okf_index",
        "okf_read",
        "okf_search",
        "compute_installment_refund",
        "compute_proration",
        "build_discount_note",
        "calculate",
    }
    assert "google_search" not in names
    assert "Never infer a" in module.SYSTEM_INSTRUCTION
    assert "/system-navigation/screen-map" in module.SYSTEM_INSTRUCTION
    assert "/order-entry/" in module.SYSTEM_INSTRUCTION
    assert "/system-navigation/rep-shorthand" in module.SYSTEM_INSTRUCTION


def test_tool_errors_are_returned_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_agent_module(monkeypatch)
    tool = SimpleNamespace(name="okf_read")

    response = module.report_tool_error(
        tool=tool,
        args={"concept": "/skus/typo"},
        tool_context=None,
        error=OKFError("knowledge concept not found: /skus/typo"),
    )
    internal = module.report_tool_error(
        tool=tool, args={}, tool_context=None, error=OSError("/Users/someone/private")
    )

    assert module.root_agent.on_tool_error_callback is module.report_tool_error
    assert "knowledge concept not found: /skus/typo" in response["error"]
    assert "Do not estimate" in response["error"]
    assert "/Users/someone" not in internal["error"]
