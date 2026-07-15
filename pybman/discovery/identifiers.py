"""Normalization of the identifiers used for research-data discovery.

Both DOIs and ORCID iDs occur in the wild as bare identifiers, with scheme
prefixes (``doi:``) or as resolver URLs. Providers compare and query by the
canonical form, so everything entering the discovery package goes through
these helpers first.
"""

from __future__ import annotations

import re

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

_ORCID_PREFIXES = ("https://orcid.org/", "http://orcid.org/", "orcid.org/")
_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def normalize_doi(value: str) -> str:
    """Return the canonical (lowercase, bare) form of a DOI.

    Accepts resolver URLs (``https://doi.org/10.x/y``) and ``doi:`` prefixes.
    DOIs are case-insensitive by specification, so the result is lowercased
    to make cross-provider comparison reliable.

    Raises:
        ValueError: if ``value`` is not a syntactically valid DOI.
    """
    doi = value.strip()
    for prefix in _DOI_PREFIXES:
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix) :]
            break
    if doi.lower().startswith("doi:"):
        doi = doi[4:]
    doi = doi.lower()
    if not _DOI_RE.match(doi):
        raise ValueError(f"not a valid DOI: {value!r}")
    return doi


def normalize_orcid(value: str) -> str:
    """Return the canonical 16-character ORCID iD (``0000-0000-0000-000X``).

    Accepts ``https://orcid.org/...`` URLs. The checksum character ``X`` is
    uppercased as required by the ORCID specification.

    Raises:
        ValueError: if ``value`` is not a syntactically valid ORCID iD.
    """
    orcid = value.strip()
    lowered = orcid.lower()
    for prefix in _ORCID_PREFIXES:
        if lowered.startswith(prefix):
            orcid = orcid[len(prefix) :]
            break
    orcid = orcid.strip("/").upper()
    if not _ORCID_RE.match(orcid):
        raise ValueError(f"not a valid ORCID iD: {value!r}")
    return orcid
