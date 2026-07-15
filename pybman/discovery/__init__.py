"""Research-data discovery: find datasets for a publication DOI or an ORCID.

Answers the question "do research data exist for this work / researcher?"
by querying several public scholarly infrastructure APIs and aggregating
the results. See docs/RESEARCH_DATA_DISCOVERY.md for a capability matrix
of the services.

Quick start:
    >>> from pybman.discovery import DataDiscovery
    >>> report = DataDiscovery().for_doi("10.1038/s41586-020-2649-2")
    >>> report.found, report.summary()  # doctest: +SKIP
"""

from ._client import DiscoveryError, Provider, make_session
from .aea import AeaDataProvider
from .aggregator import DataDiscovery, SupportsDiscovery
from .b2find import B2FindProvider
from .crossref import CrossrefProvider
from .datacite import DataCiteProvider
from .europepmc import EuropePmcProvider
from .google import google_dataset_search_url
from .identifiers import normalize_doi, normalize_orcid
from .models import DatasetHit, DiscoveryReport, ProviderResult
from .openaire import OpenAIREProvider
from .orcid import OrcidProvider
from .osf import OsfProvider
from .scholexplorer import ScholexplorerProvider

__all__ = [
    "AeaDataProvider",
    "B2FindProvider",
    "CrossrefProvider",
    "DataCiteProvider",
    "DataDiscovery",
    "DatasetHit",
    "DiscoveryError",
    "DiscoveryReport",
    "EuropePmcProvider",
    "OpenAIREProvider",
    "OrcidProvider",
    "OsfProvider",
    "Provider",
    "ProviderResult",
    "ScholexplorerProvider",
    "SupportsDiscovery",
    "google_dataset_search_url",
    "make_session",
    "normalize_doi",
    "normalize_orcid",
]
