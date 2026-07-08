from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from .utils import load_json, now_kst, save_json

MAX_CACHED_HTML_CHARS = 500_000


class HttpStateCache:
    def __init__(self, path: Path):
        self.path = path
        dictLoadedState = load_json(path, {})
        self.dictState = dictLoadedState if isinstance(dictLoadedState, dict) else {}
        self.lock = threading.Lock()

    def conditional_headers(self, sUrl: str) -> dict[str, str]:
        with self.lock:
            dictEntry = dict(self.dictState.get(sUrl, {}))

        dictHeaders: dict[str, str] = {}
        sEtag = str(dictEntry.get("etag", ""))
        sLastModified = str(dictEntry.get("last_modified", ""))

        if sEtag:
            dictHeaders["If-None-Match"] = sEtag
        if sLastModified:
            dictHeaders["If-Modified-Since"] = sLastModified

        return dictHeaders

    def cached_value(self, sUrl: str, sKey: str) -> str:
        with self.lock:
            return str(self.dictState.get(sUrl, {}).get(sKey, ""))

    def content_matches(self, sUrl: str, bytesContent: bytes) -> bool:
        sContentHash = hashlib.sha256(bytesContent).hexdigest()

        with self.lock:
            return self.dictState.get(sUrl, {}).get("content_hash") == sContentHash

    def update(self, sUrl: str, dictHeaders: dict, bytesContent: bytes, **dictValues: str) -> None:
        if len(dictValues.get("html", "")) > MAX_CACHED_HTML_CHARS:
            dictValues["html"] = ""

        with self.lock:
            dictEntry = dict(self.dictState.get(sUrl, {}))
            dictEntry.update({
                "etag": str(dictHeaders.get("ETag", "")),
                "last_modified": str(dictHeaders.get("Last-Modified", "")),
                "content_hash": hashlib.sha256(bytesContent).hexdigest(),
                "checked_at": now_kst().isoformat(timespec="seconds"),
                **dictValues,
            })
            self.dictState[sUrl] = dictEntry

    def save(self) -> None:
        with self.lock:
            lstEntries = sorted(
                self.dictState.items(),
                key=lambda tupleEntry: str(tupleEntry[1].get("checked_at", "")),
                reverse=True,
            )
            dictSnapshot = dict(lstEntries[:1000])

        save_json(self.path, dictSnapshot, compact=True)
