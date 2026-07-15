"""Google Dataset Search — link building only.

Google Dataset Search (https://datasetsearch.research.google.com) indexes
schema.org/Dataset markup across the web but offers **no public API**; the
only supported integration is handing the user a search URL.
"""

from __future__ import annotations

from urllib.parse import urlencode

SEARCH_URL = "https://datasetsearch.research.google.com/search"


def google_dataset_search_url(query: str) -> str:
    """A Google Dataset Search URL for ``query`` (e.g. a DOI or author name)."""
    return f"{SEARCH_URL}?{urlencode({'query': query})}"
