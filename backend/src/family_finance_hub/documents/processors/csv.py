import csv
from dataclasses import dataclass
from io import StringIO

from .ports import DocumentProcessor


@dataclass(frozen=True)
class ParsedCsv:
    headers: tuple[str, ...]
    rows: tuple[dict[str | None, str | None], ...]


class CsvDocumentProcessor(DocumentProcessor[ParsedCsv]):
    def process(self, content: bytes) -> ParsedCsv:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV 缺少標題列")
        return ParsedCsv(tuple(reader.fieldnames), tuple(dict(row) for row in reader))
