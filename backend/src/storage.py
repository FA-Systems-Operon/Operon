"""Where uploaded document files are kept.

Endpoints only use the DocumentStorage interface, so the local-disk version
below could later be swapped for cloud storage (e.g. S3) without touching them.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from src.config import settings


class DocumentStorage(ABC):
    """Saves, reads, and deletes file contents by key (e.g. "<client_id>/<document_id>")."""

    @abstractmethod
    def save(self, key: str, data: bytes) -> None:
        """Store data under key. Raises FileExistsError if the key is taken."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Return the contents stored under key. Raises FileNotFoundError if missing."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the file for key. Does nothing if it doesn't exist."""


class LocalFileStorage(DocumentStorage):
    """Stores each file on disk at <root>/<key>."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path_for(self, key: str) -> Path:
        path = (self.root / key).resolve()
        # Reject keys like "../../etc/passwd" that would escape the storage folder.
        if not path.is_relative_to(self.root):
            raise ValueError(f"Invalid storage key: {key!r}")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # "xb" = create a new file and fail if it exists, so nothing is overwritten.
        with path.open("xb") as f:
            f.write(data)

    def read(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)


def get_storage() -> DocumentStorage:
    """FastAPI dependency. Tests override it to use a temporary folder."""
    return LocalFileStorage(settings.STORAGE_DIR)
