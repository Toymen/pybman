"""Client for the CoNE authority service (``{base_url}/cone``).

CoNE (Control of Named Entities) backs PubMan's controlled vocabularies:
persons, journals, languages, and more. It is a separate service next to the
REST API and is publicly readable.
"""

from __future__ import annotations

from typing import Any

from pybman._http import Transport

#: Well-known CoNE vocabulary names.
PERSONS = "persons"
JOURNALS = "journals"
LANGUAGES = "iso639-3"


class ConeAPI:
    """Read access to CoNE vocabularies (persons, journals, languages, ...)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    # -- generic vocabulary access ---------------------------------------

    def all(self, vocabulary: str) -> list[dict[str, Any]]:
        """GET /cone/{vocabulary}/all — every entry as ``{id, value}`` pairs."""
        result: list[dict[str, Any]] = self._transport.request_json(
            "GET", f"{self._transport.cone_url}/{vocabulary}/all", params={"format": "json"}
        )
        return result

    def query(self, vocabulary: str, q: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        """GET /cone/{vocabulary}/query — autocomplete-style search."""
        result: list[dict[str, Any]] = (
            self._transport.request_json(
                "GET",
                f"{self._transport.cone_url}/{vocabulary}/query",
                params={"q": q, "format": "json", "n": limit},
            )
            or []
        )
        return result

    def resource(self, vocabulary: str, entity_id: str) -> dict[str, Any]:
        """GET /cone/{vocabulary}/resource/{id} — full details of one entry.

        Accepts bare ids (``persons32341``), CoNE paths or full URLs.
        """
        entity_id = entity_id.rstrip("/").split("/")[-1]
        result: dict[str, Any] = self._transport.request_json(
            "GET",
            f"{self._transport.cone_url}/{vocabulary}/resource/{entity_id}",
            params={"format": "json"},
        )
        return result

    # -- persons -----------------------------------------------------------

    def persons(self) -> list[dict[str, Any]]:
        """All person entries (``{id, value}``)."""
        return self.all(PERSONS)

    def person(self, person_id: str) -> dict[str, Any]:
        """Details of one person (names, affiliations, identifiers)."""
        return self.resource(PERSONS, person_id)

    def query_persons(self, q: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        return self.query(PERSONS, q, limit=limit)

    # -- journals ------------------------------------------------------------

    def journals(self) -> list[dict[str, Any]]:
        return self.all(JOURNALS)

    def journal(self, journal_id: str) -> dict[str, Any]:
        return self.resource(JOURNALS, journal_id)

    def query_journals(self, q: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        return self.query(JOURNALS, q, limit=limit)

    # -- languages (ISO 639-3) -------------------------------------------------

    def languages(self) -> list[dict[str, Any]]:
        return self.all(LANGUAGES)

    def language(self, language_id: str) -> dict[str, Any]:
        return self.resource(LANGUAGES, language_id)

    def query_languages(self, q: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        return self.query(LANGUAGES, q, limit=limit)
