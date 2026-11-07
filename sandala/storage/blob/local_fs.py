from __future__ import annotations

from pathlib import Path


class LocalFsBlobStorage:
    backend_name = "local_fs"

    def __init__(self, root: str):
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> dict:
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"key": key, "content_type": content_type, "content_length": len(data)}

    def open(self, key: str) -> dict:
        path = self._path_for_key(key)
        return {
            "stream": path.open("rb"),
            "content_length": path.stat().st_size,
        }

    def delete(self, key: str) -> None:
        path = self._path_for_key(key)
        if path.exists():
            path.unlink()

    def _path_for_key(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        if self._root not in candidate.parents and candidate != self._root:
            raise ValueError("Invalid blob storage key")
        return candidate
