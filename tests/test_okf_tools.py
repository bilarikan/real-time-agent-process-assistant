from __future__ import annotations

from pathlib import Path

import pytest

from app.sales_agent.okf_search_index import KnowledgeSearchIndex, OKFError
from app.sales_agent.okf_tools import (
    knowledge_bundle_root,
    okf_index,
    okf_read,
    okf_search,
    reset_knowledge_index_cache,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def configured_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_BUNDLE_PATH", str(ROOT / "knowledge"))
    monkeypatch.setenv("OKF_TOOL_TOKEN_LIMIT", "3000")
    reset_knowledge_index_cache()
    yield
    reset_knowledge_index_cache()


def _concept_files() -> list[Path]:
    return [
        path
        for path in (ROOT / "knowledge").rglob("*.md")
        if path.name not in {"index.md", "log.md"}
    ]


def test_index_loads_every_concept_in_the_bundle() -> None:
    index = KnowledgeSearchIndex.load(ROOT / "knowledge")

    assert len(index.documents) == len(_concept_files())
    assert "/skus/acme-suite-plans" in index.documents
    assert "/system-navigation/screen-map" in index.documents
    assert "/pricing-and-discounts/proration" in index.documents


def test_exact_sku_search_finds_current_authority() -> None:
    result = okf_search("ACME-PLUS-A")

    assert "Concept ID: /skus/acme-suite-plans" in result
    assert "/skus/superseded/old-price-list" not in result


@pytest.mark.parametrize(
    ("query", "expected_first"),
    [
        ("Acme Suite Pro plan SKU", "/skus/acme-suite-plans"),
        ("Payment information is not complete", "/troubleshooting/common-errors"),
        ("wrong discount code PRICE-FIX-UP", "/pricing-and-discounts/discount-codes"),
        ("installment refund amount clearing", "/pricing-and-discounts/installment-refunds"),
        ("prorated upgrade days remaining", "/pricing-and-discounts/proration"),
        ("how do I create a new account", "/system-navigation/create-account"),
        ("what to check before saving the order", "/system-navigation/order-checklist"),
        ("new customer subscription walkthrough", "/order-entry/new-customer-subscription"),
        ("upgrade a plan mid-term", "/order-entry/upgrade-plan"),
        ("what does the rep mean by the plan line", "/system-navigation/rep-shorthand"),
    ],
)
def test_demo_queries_have_deterministic_top_results(query: str, expected_first: str) -> None:
    result = okf_search(query)
    first_result = next(
        line.removeprefix("- Concept ID: ")
        for line in result.splitlines()
        if line.startswith("- Concept ID: ")
    )

    assert first_result == expected_first


def test_deprecated_concepts_are_opt_in() -> None:
    default_result = okf_search("ACME-OLD-1 retired", limit=10)
    historical_result = okf_search(
        "ACME-OLD-1 retired",
        include_deprecated=True,
        limit=10,
    )

    assert "/skus/superseded/old-price-list" not in default_result
    assert "/skus/superseded/old-price-list" in historical_result
    assert "superseded_by=/skus/acme-suite-plans.md" in historical_result


def test_index_and_read_return_auditable_concept_ids() -> None:
    index_result = okf_index("/pricing-and-discounts")
    concept_result = okf_read("/pricing-and-discounts/discount-codes")

    assert "Concept index: /pricing-and-discounts/index.md" in index_result
    assert "Concept ID: /pricing-and-discounts/discount-codes" in concept_result
    assert "PRORATE-DOWN" in concept_result


@pytest.mark.parametrize(
    "unsafe_path",
    ["../PRD", "/../PRD", "skus/../../PRD", "/etc/passwd"],
)
def test_read_rejects_path_traversal_and_non_markdown(unsafe_path: str) -> None:
    with pytest.raises(OKFError):
        okf_read(unsafe_path)


def test_tool_response_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OKF_TOOL_TOKEN_LIMIT", "100")

    result = okf_read("/skus/acme-suite-plans")

    assert len(result) <= 400
    assert "[TRUNCATED:" in result


def test_relative_bundle_path_resolves_from_the_project_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KNOWLEDGE_BUNDLE_PATH", "./knowledge")
    reset_knowledge_index_cache()

    assert knowledge_bundle_root() == ROOT / "knowledge"
    assert "Concept ID: /skus/acme-suite-plans" in okf_search("ACME-PLUS-A")
