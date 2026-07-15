"""Conservative metadata matching shared by title-based providers."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize_text(value: str) -> str:
    """Normalize case, accents and punctuation for metadata comparison."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))


def title_tokens(value: str) -> set[str]:
    return set(normalize_text(value).split())


def title_match_score(publication_title: str, dataset_title: str) -> float:
    """Return a conservative similarity score in the inclusive range 0..1."""
    publication = normalize_text(publication_title)
    dataset = normalize_text(dataset_title)
    if not publication or not dataset:
        return 0.0
    if publication in dataset:
        return 1.0
    publication_tokens = set(publication.split())
    coverage = len(publication_tokens & set(dataset.split())) / len(publication_tokens)
    return max(coverage, SequenceMatcher(None, publication, dataset).ratio())


def surname(value: str) -> str:
    parts = normalize_text(value).split()
    return parts[-1] if parts else ""


def has_surname_overlap(publication_authors: tuple[str, ...], candidate_names: list[str]) -> bool:
    """Require at least one normalized surname shared by both metadata records."""
    if not publication_authors:
        return False
    publication_surnames = {surname(author) for author in publication_authors} - {""}
    candidate_surnames = {surname(name) for name in candidate_names} - {""}
    return bool(publication_surnames & candidate_surnames)
