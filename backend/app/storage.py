"""Where uploaded receipt files are kept.

Locally they go to a folder on disk; in production an S3-backed class with the same
methods will replace it (stage 9).
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Protocol

from fastapi import Depends

from app.config import get_settings


class FileStorage(Protocol):
    def save(self, key: str, data: bytes, content_type: str) -> None: ...

    def read(self, key: str) -> bytes: ...


class LocalFileStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Invalid storage key: {key!r}")
        return path

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()


@lru_cache
def get_storage() -> FileStorage:
    """FastAPI dependency returning the configured storage. Tests override this."""
    return LocalFileStorage(get_settings().storage_dir)


StorageDep = Annotated[FileStorage, Depends(get_storage)]
