"""File staging endpoint (``/staging``) for uploads."""

from __future__ import annotations

import os
from typing import IO

from pybman._http import Transport


class StagingAPI:
    """Stage files before attaching them to items.

    Files that should be attached to an item must be uploaded to the staging
    area first; the returned staged-file id is then referenced from the
    item's ``files`` entry (``"storage": "INTERNAL_MANAGED"``, ``"content":
    "<staged id>"``) when creating or updating the item.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def upload(
        self,
        source: str | os.PathLike[str] | bytes | IO[bytes],
        *,
        filename: str | None = None,
    ) -> str:
        """POST /staging/{componentName} — upload a file, return its staged id.

        ``source`` may be a path, raw bytes, or a binary file object. The
        ``filename`` (defaults to the basename of a path source) becomes the
        component name and must carry the correct file extension.

        Requires authentication.
        """
        data: bytes | IO[bytes]
        if isinstance(source, bytes):
            if not filename:
                raise ValueError("filename is required when uploading raw bytes")
            data = source
        elif hasattr(source, "read"):
            if not filename:
                raise ValueError("filename is required when uploading from a file object")
            data = source  # type: ignore[assignment]
        else:
            path = os.fspath(source)
            filename = filename or os.path.basename(path)
            with open(path, "rb") as fh:
                data = fh.read()

        response = self._transport.request(
            "POST",
            f"/staging/{filename}",
            data=data,  # type: ignore[arg-type]
            headers={"Content-Type": "application/octet-stream"},
            authenticated=True,
        )
        return response.text.strip().strip('"')
