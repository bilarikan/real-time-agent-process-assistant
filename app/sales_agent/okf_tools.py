"""Read-only function tools for the local Open Knowledge Format bundle."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path, PurePosixPath

from .okf_search_index import KnowledgeSearchIndex, OKFError

LOGGER = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TRUNCATION_MARKER = "\n\n[TRUNCATED: local knowledge tool response limit reached]"


def okf_index(path: str = "/") -> str:
    """List knowledge available at a bundle location.

    Returns that directory's index.md. Start here when the concept location is
    unknown. The path is bundle-relative, for example "/" or "/skus".
    """
    index = get_knowledge_index()
    index_path = _resolve_bundle_path(index.bundle_root, path, index_file=True)
    if not index_path.is_file():
        raise OKFError(f"knowledge index not found: {path}")

    concept_id = _bundle_id(index.bundle_root, index_path)
    LOGGER.info("okf_index path=%r result=%s", path, concept_id)
    return _bounded(f"Concept index: {concept_id}\n\n{index_path.read_text(encoding='utf-8')}")


def okf_read(concept: str) -> str:
    """Read one concept document in full.

    Use a bundle-relative concept ID such as "/skus/cloud-and-desktop". If the
    returned status is deprecated, follow its superseded_by pointer.
    """
    index = get_knowledge_index()
    concept_path = _resolve_bundle_path(index.bundle_root, concept, index_file=False)
    if not concept_path.is_file():
        raise OKFError(f"knowledge concept not found: {concept}")
    if concept_path.name in {"index.md", "log.md"}:
        raise OKFError("use okf_index to read index files")

    concept_id = _bundle_id(index.bundle_root, concept_path, strip_suffix=True)
    LOGGER.info("okf_read concept=%r result=%s", concept, concept_id)
    text = concept_path.read_text(encoding="utf-8")
    return _bounded(f"Concept ID: {concept_id}\n\n{text}")


def okf_search(
    query: str,
    tags: list[str] | None = None,
    include_deprecated: bool = False,
    limit: int = 5,
) -> str:
    """Search the local knowledge bundle and return ranked concept IDs.

    Deprecated concepts are excluded unless include_deprecated is true. Read a
    selected result with okf_read before answering policy or SKU questions.
    """
    hits = get_knowledge_index().search(
        query,
        tags=tags,
        include_deprecated=include_deprecated,
        limit=limit,
    )
    result_ids = [hit.concept_id for hit in hits]
    LOGGER.info(
        "okf_search query=%r tags=%r include_deprecated=%s limit=%s results=%r",
        query,
        tags,
        include_deprecated,
        limit,
        result_ids,
    )

    if not hits:
        return f"No local knowledge results for: {query}"

    lines = [f"Search results for: {query}"]
    for hit in hits:
        status = f"status={hit.status}"
        if hit.superseded_by:
            status += f", superseded_by={hit.superseded_by}"
        lines.extend(
            [
                "",
                f"- Concept ID: {hit.concept_id}",
                f"  Title: {hit.title}",
                f"  {status}",
                f"  Description: {hit.description}",
                f"  Match: {hit.snippet}",
            ]
        )
    return _bounded("\n".join(lines))


def preload_knowledge_index() -> KnowledgeSearchIndex:
    """Build and cache the search index during application startup."""
    return get_knowledge_index()


def get_knowledge_index() -> KnowledgeSearchIndex:
    return _load_index(str(knowledge_bundle_root()))


def knowledge_bundle_root() -> Path:
    """Resolve KNOWLEDGE_BUNDLE_PATH; a relative path is relative to the project root."""
    configured = Path(os.getenv("KNOWLEDGE_BUNDLE_PATH", "knowledge")).expanduser()
    if not configured.is_absolute():
        configured = _PROJECT_ROOT / configured
    return configured.resolve()


@lru_cache(maxsize=4)
def _load_index(bundle_root: str) -> KnowledgeSearchIndex:
    index = KnowledgeSearchIndex.load(Path(bundle_root))
    LOGGER.info("loaded %s OKF concepts from %s", len(index.documents), bundle_root)
    return index


def reset_knowledge_index_cache() -> None:
    """Clear the process cache. Intended for tests and offline rebuilds."""
    _load_index.cache_clear()


def _resolve_bundle_path(root: Path, requested: str, *, index_file: bool) -> Path:
    requested = requested.strip()
    if not requested:
        raise OKFError("knowledge path must not be empty")

    relative_text = requested.lstrip("/")
    relative = PurePosixPath(relative_text)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise OKFError(f"unsafe knowledge path: {requested}")

    candidate = root.joinpath(*relative.parts) if relative.parts else root
    if index_file:
        candidate = candidate / "index.md" if candidate.suffix != ".md" else candidate
    elif candidate.suffix == "":
        candidate = candidate.with_suffix(".md")
    elif candidate.suffix != ".md":
        raise OKFError("knowledge concepts must be Markdown files")

    resolved = candidate.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise OKFError(f"unsafe knowledge path: {requested}")
    return resolved


def _bundle_id(root: Path, path: Path, *, strip_suffix: bool = False) -> str:
    relative = path.relative_to(root).as_posix()
    if strip_suffix and relative.endswith(".md"):
        relative = relative[:-3]
    return f"/{relative}"


def _bounded(text: str) -> str:
    try:
        token_limit = int(os.getenv("OKF_TOOL_TOKEN_LIMIT", "3000"))
    except ValueError as exc:
        raise OKFError("OKF_TOOL_TOKEN_LIMIT must be an integer") from exc
    if token_limit < 100:
        raise OKFError("OKF_TOOL_TOKEN_LIMIT must be at least 100")

    character_limit = token_limit * 4
    if len(text) <= character_limit:
        return text
    keep = character_limit - len(_TRUNCATION_MARKER)
    return f"{text[:keep].rstrip()}{_TRUNCATION_MARKER}"
