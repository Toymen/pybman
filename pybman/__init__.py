"""pybman — Python client for MPG.PuRe, the Max Planck Society's
publication repository, via the PubMan REST API."""

from pybman.__about__ import __version__
from pybman.client import Client
from pybman.data import DataSet
from pybman.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    NotFoundError,
    PubManError,
    PubManHTTPError,
    ServerError,
)
from pybman.inspector import Inspector
from pybman.local import LocalData
from pybman.models import SearchResult, UserAccount

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "BadRequestError",
    "Client",
    "DataSet",
    "Inspector",
    "LocalData",
    "NotFoundError",
    "PubManError",
    "PubManHTTPError",
    "SearchResult",
    "ServerError",
    "UserAccount",
    "__version__",
]

name = "pybman"
