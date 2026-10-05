"""Validate this project's Open Knowledge Format v0.2 profile."""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

_LINK_RE = re.compile(r"\]\((/[^)#]+\.md)(?:#[^)]+)?\)")
_RESERVED = {"index.md", "log.md"}


def validate_bundle(root: Path) -> list[str]:
    root = root.expanduser().resolve()
    errors: list[str] = []
    if not root.is_dir():
        return [f"bundle does not exist: {root}"]
    if not (root / "index.md").is_file():
        errors.append("missing root index.md")

    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        metadata, parse_error = _frontmatter(text)
        relative = path.relative_to(root)

        if path.name not in _RESERVED:
            if parse_error:
                errors.append(f"{relative}: {parse_error}")
                continue
            if not str(metadata.get("type", "")).strip():
                errors.append(f"{relative}: missing non-empty frontmatter type")
        elif path == root / "index.md":
            if parse_error:
                errors.append(f"{relative}: {parse_error}")
            elif str(metadata.get("okf_version", "")) != "0.2":
                errors.append(f'{relative}: okf_version must be "0.2"')

        if metadata:
            _validate_timestamps(relative, metadata, errors)
            _validate_supersession(root, relative, metadata, errors)
            _validate_source_files(path, relative, metadata, errors)

        for target in _LINK_RE.findall(text):
            resolved = root / target.lstrip("/")
            if not resolved.is_file():
                errors.append(f"{relative}: broken internal link {target}")

    concept_parents = {path.parent for path in root.rglob("*.md") if path.name not in _RESERVED}
    for parent in sorted(concept_parents):
        if not (parent / "index.md").is_file():
            errors.append(f"{parent.relative_to(root)}: missing index.md")

    return errors


def _frontmatter(text: str) -> tuple[dict[str, Any], str | None]:
    if not text.startswith("---\n"):
        return {}, "missing YAML frontmatter"
    marker = text.find("\n---\n", 4)
    if marker < 0:
        return {}, "unterminated YAML frontmatter"
    try:
        metadata = yaml.safe_load(text[4:marker]) or {}
    except yaml.YAMLError as exc:
        return {}, f"invalid YAML frontmatter: {exc}"
    if not isinstance(metadata, dict):
        return {}, "YAML frontmatter must be a mapping"
    return metadata, None


def _validate_timestamps(
    relative: Path,
    metadata: dict[str, Any],
    errors: list[str],
) -> None:
    candidates: list[tuple[str, object]] = []
    for field in ("generated", "verified"):
        value = metadata.get(field)
        if isinstance(value, dict) and "at" in value:
            candidates.append((f"{field}.at", value["at"]))
    if "stale_after" in metadata:
        candidates.append(("stale_after", metadata["stale_after"]))

    for field, value in candidates:
        if not _has_utc_offset(value):
            errors.append(f"{relative}: {field} must be a timestamp with UTC offset")


def _has_utc_offset(value: object) -> bool:
    if isinstance(value, datetime):
        return value.tzinfo is not None and value.utcoffset() is not None
    if isinstance(value, date):
        return False
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _validate_supersession(
    root: Path,
    relative: Path,
    metadata: dict[str, Any],
    errors: list[str],
) -> None:
    superseded_by = metadata.get("superseded_by")
    if not superseded_by:
        return
    target = str(superseded_by)
    if not target.startswith("/") or not target.endswith(".md"):
        errors.append(f"{relative}: superseded_by must be a bundle-absolute .md path")
        return
    if not (root / target.lstrip("/")).is_file():
        errors.append(f"{relative}: superseded_by target does not exist: {target}")


def _validate_source_files(
    document_path: Path,
    relative: Path,
    metadata: dict[str, Any],
    errors: list[str],
) -> None:
    sources = metadata.get("sources", [])
    if not isinstance(sources, list):
        errors.append(f"{relative}: sources must be a list")
        return
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"{relative}: sources[{index}] must be a mapping")
            continue
        resource = str(source.get("resource", ""))
        if resource.startswith("file:"):
            target = (document_path.parent / resource.removeprefix("file:")).resolve()
            if not target.is_file():
                errors.append(f"{relative}: source file does not exist: {resource}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", nargs="?", default="knowledge", type=Path)
    args = parser.parse_args()

    errors = validate_bundle(args.bundle)
    if errors:
        print("OKF validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    concepts = sum(path.name not in _RESERVED for path in args.bundle.resolve().rglob("*.md"))
    print(f"OKF validation passed: {concepts} concepts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
