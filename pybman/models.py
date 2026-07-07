"""Typed value objects and controlled vocabularies of the PubMan REST API.

Records themselves are kept as plain dictionaries (the PubMan item schema is
large and evolves server-side); this module provides the stable envelope
types and the enumerations published in the service's OpenAPI specification
(``https://pure.mpg.de/rest/v3/api-docs``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "CreatorRole",
    "CreatorType",
    "ExportFormat",
    "FileStorage",
    "FileVisibility",
    "Genre",
    "IdentifierType",
    "ItemState",
    "SearchResult",
    "SourceGenre",
    "UserAccount",
]

#: A PubMan record as returned inside search results: a dict with
#: ``data`` (the item), ``persistenceId``, and envelope fields.
Record = dict[str, Any]

#: A bare PubMan item (``ItemVersionVO``) as returned by ``GET /items/{id}``.
Item = dict[str, Any]


@dataclass(frozen=True)
class SearchResult:
    """Envelope of ``POST /items/search`` (``SearchRetrieveResponseVO``)."""

    number_of_records: int
    records: list[Record] = field(default_factory=list)
    scroll_id: str | None = None
    version: str | None = None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> SearchResult:
        return cls(
            number_of_records=int(payload.get("numberOfRecords", 0)),
            records=list(payload.get("records") or []),
            scroll_id=payload.get("scrollId"),
            version=payload.get("version"),
        )

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self) -> Any:
        return iter(self.records)


@dataclass(frozen=True)
class UserAccount:
    """The authenticated user as reported by ``GET /login/who``."""

    object_id: str
    name: str = ""
    login_name: str = ""
    email: str = ""
    active: bool = True
    grants: dict[str, list[str]] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def roles(self) -> list[str]:
        return sorted(self.grants)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> UserAccount:
        grants: dict[str, list[str]] = {}
        for grant in payload.get("grantList") or []:
            role = grant.get("role", "")
            grants.setdefault(role, [])
            if "objectRef" in grant:
                grants[role].append(grant["objectRef"])
        return cls(
            object_id=payload.get("objectId", ""),
            name=payload.get("name", ""),
            login_name=payload.get("loginname", ""),
            email=payload.get("email", ""),
            active=bool(payload.get("active", True)),
            grants=grants,
            raw=payload,
        )


class ItemState(str, Enum):
    """Public / version state of an item."""

    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    RELEASED = "RELEASED"
    WITHDRAWN = "WITHDRAWN"
    IN_REVISION = "IN_REVISION"


class ExportFormat(str, Enum):
    """Values of the ``format`` parameter of search and export endpoints."""

    JSON = "json"
    ESCIDOC_ITEMLIST_XML = "eSciDoc_Itemlist_Xml"
    BIBTEX = "BibTex"
    ENDNOTE = "EndNote"
    MARC_XML = "Marc_Xml"
    PDF = "pdf"
    DOCX = "docx"
    HTML_PLAIN = "html_plain"
    HTML_LINKED = "html_linked"
    JSON_CITATION = "json_citation"
    ESCIDOC_SNIPPET = "escidoc_snippet"


class CitationStyle(str, Enum):
    """Values of the ``citation`` parameter (required by some formats)."""

    APA = "APA"
    APA_CJK = "APA(CJK)"
    AJP = "AJP"
    JUS = "JUS"
    CSL = "CSL"


class FileStorage(str, Enum):
    INTERNAL_MANAGED = "INTERNAL_MANAGED"
    EXTERNAL_URL = "EXTERNAL_URL"


class FileVisibility(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    AUDIENCE = "AUDIENCE"


class CreatorType(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"


class CreatorRole(str, Enum):
    ACTOR = "ACTOR"
    ADVISOR = "ADVISOR"
    APPLICANT = "APPLICANT"
    ARTIST = "ARTIST"
    AUTHOR = "AUTHOR"
    CINEMATOGRAPHER = "CINEMATOGRAPHER"
    COMMENTATOR = "COMMENTATOR"
    CONTRIBUTOR = "CONTRIBUTOR"
    DEVELOPER = "DEVELOPER"
    DIRECTOR = "DIRECTOR"
    EDITOR = "EDITOR"
    HONOREE = "HONOREE"
    ILLUSTRATOR = "ILLUSTRATOR"
    INTERVIEWEE = "INTERVIEWEE"
    INTERVIEWER = "INTERVIEWER"
    INVENTOR = "INVENTOR"
    PAINTER = "PAINTER"
    PHOTOGRAPHER = "PHOTOGRAPHER"
    PRODUCER = "PRODUCER"
    REFEREE = "REFEREE"
    SOUND_DESIGNER = "SOUND_DESIGNER"
    TRANSCRIBER = "TRANSCRIBER"
    TRANSLATOR = "TRANSLATOR"


class Genre(str, Enum):
    ARTICLE = "ARTICLE"
    BLOG_POST = "BLOG_POST"
    BOOK = "BOOK"
    BOOK_ITEM = "BOOK_ITEM"
    BOOK_REVIEW = "BOOK_REVIEW"
    CASE_NOTE = "CASE_NOTE"
    CASE_STUDY = "CASE_STUDY"
    COLLECTED_EDITION = "COLLECTED_EDITION"
    COMMENTARY = "COMMENTARY"
    CONFERENCE_PAPER = "CONFERENCE_PAPER"
    CONFERENCE_REPORT = "CONFERENCE_REPORT"
    CONTRIBUTION_TO_COLLECTED_EDITION = "CONTRIBUTION_TO_COLLECTED_EDITION"
    CONTRIBUTION_TO_COMMENTARY = "CONTRIBUTION_TO_COMMENTARY"
    CONTRIBUTION_TO_ENCYCLOPEDIA = "CONTRIBUTION_TO_ENCYCLOPEDIA"
    CONTRIBUTION_TO_FESTSCHRIFT = "CONTRIBUTION_TO_FESTSCHRIFT"
    CONTRIBUTION_TO_HANDBOOK = "CONTRIBUTION_TO_HANDBOOK"
    COURSEWARE_LECTURE = "COURSEWARE_LECTURE"
    DATA_PUBLICATION = "DATA_PUBLICATION"
    EDITORIAL = "EDITORIAL"
    ENCYCLOPEDIA = "ENCYCLOPEDIA"
    FESTSCHRIFT = "FESTSCHRIFT"
    FILM = "FILM"
    HANDBOOK = "HANDBOOK"
    INTERVIEW = "INTERVIEW"
    ISSUE = "ISSUE"
    JOURNAL = "JOURNAL"
    MAGAZINE_ARTICLE = "MAGAZINE_ARTICLE"
    MANUAL = "MANUAL"
    MANUSCRIPT = "MANUSCRIPT"
    MEETING_ABSTRACT = "MEETING_ABSTRACT"
    MONOGRAPH = "MONOGRAPH"
    MULTI_VOLUME = "MULTI_VOLUME"
    NEWSPAPER = "NEWSPAPER"
    NEWSPAPER_ARTICLE = "NEWSPAPER_ARTICLE"
    OPINION = "OPINION"
    OTHER = "OTHER"
    PAPER = "PAPER"
    PATENT = "PATENT"
    POSTER = "POSTER"
    PREPRINT = "PREPRINT"
    PRE_REGISTRATION_PAPER = "PRE_REGISTRATION_PAPER"
    PROCEEDINGS = "PROCEEDINGS"
    REGISTERED_REPORT = "REGISTERED_REPORT"
    REPORT = "REPORT"
    REVIEW_ARTICLE = "REVIEW_ARTICLE"
    SERIES = "SERIES"
    SOFTWARE = "SOFTWARE"
    TALK_AT_EVENT = "TALK_AT_EVENT"
    THESIS = "THESIS"


class SourceGenre(str, Enum):
    BLOG = "BLOG"
    BOOK = "BOOK"
    COLLECTED_EDITION = "COLLECTED_EDITION"
    COMMENTARY = "COMMENTARY"
    ENCYCLOPEDIA = "ENCYCLOPEDIA"
    FESTSCHRIFT = "FESTSCHRIFT"
    HANDBOOK = "HANDBOOK"
    ISSUE = "ISSUE"
    JOURNAL = "JOURNAL"
    MULTI_VOLUME = "MULTI_VOLUME"
    NEWSPAPER = "NEWSPAPER"
    PROCEEDINGS = "PROCEEDINGS"
    RADIO_BROADCAST = "RADIO_BROADCAST"
    SERIES = "SERIES"
    TV_BROADCAST = "TV_BROADCAST"
    WEB_PAGE = "WEB_PAGE"


class IdentifierType(str, Enum):
    ADS = "ADS"
    ARXIV = "ARXIV"
    BIBTEX_CITEKEY = "BIBTEX_CITEKEY"
    BIORXIV = "BIORXIV"
    BMC = "BMC"
    CHEMRXIV = "CHEMRXIV"
    CONE = "CONE"
    DOI = "DOI"
    EARTHARXIV = "EARTHARXIV"
    EDARXIV = "EDARXIV"
    EDOC = "EDOC"
    ESCIDOC = "ESCIDOC"
    ESS_OPEN_ARCHIVE = "ESS_OPEN_ARCHIVE"
    GRANT_ID = "GRANT_ID"
    ISBN = "ISBN"
    ISI = "ISI"
    ISSN = "ISSN"
    MEDRXIV = "MEDRXIV"
    OATYPE = "OATYPE"
    OPEN_AIRE = "OPEN_AIRE"
    OTHER = "OTHER"
    PATENT_APPLICATION_NR = "PATENT_APPLICATION_NR"
    PATENT_NR = "PATENT_NR"
    PATENT_PUBLICATION_NR = "PATENT_PUBLICATION_NR"
    PII = "PII"
    PMC = "PMC"
    PMID = "PMID"
    PND = "PND"
    PSYARXIV = "PSYARXIV"
    PUBLISHER = "PUBLISHER"
    REPORT_NR = "REPORT_NR"
    RESEARCH_SQUARE = "RESEARCH_SQUARE"
    SOCARXIV = "SOCARXIV"
    SSRN = "SSRN"
    URI = "URI"
    URN = "URN"
    ZDB = "ZDB"
