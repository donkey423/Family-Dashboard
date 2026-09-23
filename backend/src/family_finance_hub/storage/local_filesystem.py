from pathlib import Path
from uuid import uuid4


class LocalFilesystemStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, content: bytes) -> str:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
            temporary.write_bytes(content)
            temporary.replace(target)
        return key

    def read(self, key: str) -> bytes:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return target.read_bytes()
