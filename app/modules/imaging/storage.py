"""Image storage behind a tiny interface so S3/GCS can replace the local filesystem later."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class ImageStorage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...
    def path(self, key: str) -> Path: ...        # local path for model/preview (cloud impls: download to temp)
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError("storage key escapes storage root")
        return p

    def save(self, key: str, data: bytes) -> None:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)  # atomic: never a half-written image

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink()
        except FileNotFoundError:
            pass
