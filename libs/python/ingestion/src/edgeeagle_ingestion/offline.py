"""Local-file acquisition; caller owns trusted paths and retention permission."""

from pathlib import Path

from edgeeagle_domain.raw import RawCapture, RawPayload


class LocalFileImporter:
    def __init__(self, path: Path, capture: RawCapture, *, max_bytes: int) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        if not isinstance(capture, RawCapture):
            raise TypeError("capture must be a RawCapture")
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        self._path = path
        self._capture = capture
        self._max_bytes = max_bytes

    def read(self) -> RawPayload:
        with self._path.open("rb") as stream:
            body = stream.read(self._max_bytes + 1)
        if len(body) > self._max_bytes:
            raise ValueError("local payload exceeds byte limit")
        return RawPayload(capture=self._capture, body=body)
