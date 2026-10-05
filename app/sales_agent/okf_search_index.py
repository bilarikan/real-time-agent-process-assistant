"""In-memory search index for the local OKF bundle."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_TOKEN_RE = re.compile(r"[$%][A-Za-z0-9]+|[A-Za-z0-9][A-Za-z0-9_-]*")
_RESERVED_FILES = {"index.md", "log.md"}
# Question words and fillers are dropped from queries so a prose-heavy concept
# cannot outrank the one that names the task, e.g. "how do I add a credit card".
_QUERY_STOPWORD_TEXT = """
a an and are as at be by can could do does for from how i in into is it me my of on or our
should so that the their then there this to us we what when where which who why will with
would you your
"""
_QUERY_STOPWORDS = frozenset(_QUERY_STOPWORD_TEXT.split())


class OKFError(ValueError):
    """Raised when the local knowledge bundle is invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    concept_id: str
    path: Path
    metadata: dict[str, Any]
    body: str

    @property
    def title(self) -> str:
        return str(self.metadata.get("title", self.concept_id))

    @property
    def description(self) -> str:
        return str(self.metadata.get("description", ""))

    @property
    def status(self) -> str:
        return str(self.metadata.get("status", "stable")).casefold()

    @property
    def tags(self) -> tuple[str, ...]:
        value = self.metadata.get("tags", [])
        if isinstance(value, str):
            return (value,)
        if not isinstance(value, list):
            return ()
        return tuple(str(tag) for tag in value)


@dataclass(frozen=True, slots=True)
class SearchHit:
    concept_id: str
    title: str
    description: str
    status: str
    superseded_by: str | None
    score: float
    snippet: str


def parse_okf_document(path: Path, bundle_root: Path) -> KnowledgeDocument:
    """Parse one non-reserved OKF Markdown document."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise OKFError(f"{path}: missing YAML frontmatter")

    marker = text.find("\n---\n", 4)
    if marker < 0:
        raise OKFError(f"{path}: unterminated YAML frontmatter")

    try:
        metadata = yaml.safe_load(text[4:marker]) or {}
    except yaml.YAMLError as exc:
        raise OKFError(f"{path}: invalid YAML frontmatter: {exc}") from exc

    if not isinstance(metadata, dict):
        raise OKFError(f"{path}: YAML frontmatter must be a mapping")
    if not str(metadata.get("type", "")).strip():
        raise OKFError(f"{path}: frontmatter must contain a non-empty type")

    relative = path.relative_to(bundle_root).with_suffix("")
    concept_id = f"/{relative.as_posix()}"
    return KnowledgeDocument(
        concept_id=concept_id,
        path=path,
        metadata=metadata,
        body=text[marker + 5 :].strip(),
    )


def tokenize(value: str) -> list[str]:
    """Tokenize prose while preserving internal business codes.

    Hyphenated words also contribute their parts, so "auto renew" matches
    "Auto-Renew" and "sold to" matches "Sold-To".
    """
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(value):
        token = match.group(0).casefold()
        tokens.append(token)
        if "-" in token:
            tokens.extend(part for part in token.split("-") if part)
    return tokens


class KnowledgeSearchIndex:
    """Small, deterministic BM25 index built once at process start."""

    def __init__(self, bundle_root: Path, documents: Iterable[KnowledgeDocument]):
        self.bundle_root = bundle_root.resolve()
        self.documents = {document.concept_id: document for document in documents}
        self._term_frequencies: dict[str, Counter[str]] = {}
        self._document_lengths: dict[str, int] = {}
        self._document_frequency: Counter[str] = Counter()

        for concept_id, document in self.documents.items():
            weighted_tags = " ".join(document.tags)
            weighted_text = " ".join(
                [
                    f"{document.title} {document.title} {document.title}",
                    f"{document.description} {document.description}",
                    f"{weighted_tags} {weighted_tags} {weighted_tags}",
                    document.body,
                ]
            )
            frequencies = Counter(tokenize(weighted_text))
            self._term_frequencies[concept_id] = frequencies
            self._document_lengths[concept_id] = sum(frequencies.values())
            self._document_frequency.update(frequencies.keys())

        document_count = max(len(self.documents), 1)
        self._average_length = (
            sum(self._document_lengths.values()) / document_count if self.documents else 1.0
        )

    @classmethod
    def load(cls, bundle_root: Path) -> KnowledgeSearchIndex:
        root = bundle_root.expanduser().resolve()
        if not root.is_dir():
            raise OKFError(f"knowledge bundle does not exist: {root}")

        documents = [
            parse_okf_document(path, root)
            for path in sorted(root.rglob("*.md"))
            if path.name not in _RESERVED_FILES
        ]
        return cls(root, documents)

    def search(
        self,
        query: str,
        *,
        tags: list[str] | None = None,
        include_deprecated: bool = False,
        limit: int = 5,
    ) -> list[SearchHit]:
        if not query.strip():
            raise OKFError("search query must not be empty")
        if limit < 1 or limit > 20:
            raise OKFError("limit must be between 1 and 20")

        query_tokens = tokenize(query)
        if not query_tokens:
            raise OKFError("search query contains no searchable terms")
        query_tokens = [
            token for token in query_tokens if token not in _QUERY_STOPWORDS
        ] or query_tokens

        required_tags = {tag.casefold() for tag in tags or []}
        scored: list[tuple[float, KnowledgeDocument]] = []
        for concept_id, document in self.documents.items():
            if document.status == "deprecated" and not include_deprecated:
                continue
            if required_tags and not required_tags.issubset(
                {tag.casefold() for tag in document.tags}
            ):
                continue

            score = self._bm25_score(concept_id, query_tokens)
            score += self._exact_match_boost(document, query_tokens)
            if score > 0:
                scored.append((score, document))

        scored.sort(key=lambda item: (-item[0], item[1].concept_id))
        return [
            SearchHit(
                concept_id=document.concept_id,
                title=document.title,
                description=document.description,
                status=document.status,
                superseded_by=_optional_string(document.metadata.get("superseded_by")),
                score=round(score, 4),
                snippet=self._snippet(document, query_tokens),
            )
            for score, document in scored[:limit]
        ]

    def _bm25_score(self, concept_id: str, query_tokens: list[str]) -> float:
        k1 = 1.5
        b = 0.75
        frequencies = self._term_frequencies[concept_id]
        document_length = self._document_lengths[concept_id]
        document_count = max(len(self.documents), 1)
        score = 0.0

        for token in set(query_tokens):
            frequency = frequencies[token]
            if not frequency:
                continue
            containing = self._document_frequency[token]
            inverse_document_frequency = math.log(
                1 + (document_count - containing + 0.5) / (containing + 0.5)
            )
            denominator = frequency + k1 * (1 - b + b * document_length / self._average_length)
            score += inverse_document_frequency * frequency * (k1 + 1) / denominator
        return score

    @staticmethod
    def _exact_match_boost(document: KnowledgeDocument, query_tokens: list[str]) -> float:
        searchable = {
            token
            for token in tokenize(
                " ".join(
                    [
                        document.title,
                        document.description,
                        " ".join(document.tags),
                        document.body,
                    ]
                )
            )
        }
        return 2.5 * sum(token in searchable for token in set(query_tokens))

    @staticmethod
    def _snippet(document: KnowledgeDocument, query_tokens: list[str]) -> str:
        plain_body = re.sub(r"[#*`>|]", " ", document.body)
        plain_body = " ".join(plain_body.split())
        folded = plain_body.casefold()
        positions = [folded.find(token) for token in query_tokens]
        positions = [position for position in positions if position >= 0]
        if not positions:
            return document.description[:320]

        start = max(min(positions) - 80, 0)
        end = min(start + 320, len(plain_body))
        prefix = "…" if start else ""
        suffix = "…" if end < len(plain_body) else ""
        return f"{prefix}{plain_body[start:end].strip()}{suffix}"


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
