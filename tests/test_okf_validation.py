from __future__ import annotations

from pathlib import Path

from tools.okf_build.validate import validate_bundle

ROOT = Path(__file__).resolve().parents[1]


def test_starter_bundle_passes_project_profile() -> None:
    assert validate_bundle(ROOT / "knowledge") == []


def test_validator_rejects_missing_type_and_broken_link(tmp_path: Path) -> None:
    bundle = tmp_path / "knowledge"
    bundle.mkdir()
    (bundle / "index.md").write_text(
        '---\nokf_version: "0.2"\n---\n[Broken](/missing.md)\n',
        encoding="utf-8",
    )
    (bundle / "bad.md").write_text("---\ntitle: Missing type\n---\nBody\n", encoding="utf-8")

    errors = validate_bundle(bundle)

    assert any("missing non-empty frontmatter type" in error for error in errors)
    assert any("broken internal link /missing.md" in error for error in errors)
