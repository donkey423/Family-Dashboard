from dataclasses import dataclass
from html.parser import HTMLParser
import re
from collections.abc import Iterable


class _TextExtractor(HTMLParser):
    _block_tags = {
        "address", "article", "aside", "blockquote", "dd", "div", "dl", "dt",
        "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
        "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p",
        "pre", "section", "table", "tbody", "tfoot", "thead", "tr",
        "ul",
    }
    _cell_tags = {"td", "th"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "br" or tag in self._block_tags:
            self._break()
        elif tag in self._cell_tags:
            self._space()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._block_tags:
            self._break()
        elif tag in self._cell_tags:
            self._space()

    def handle_data(self, data: str) -> None:
        normalized = re.sub(r"\s+", " ", data)
        if normalized:
            self.parts.append(normalized)

    def _space(self) -> None:
        if self.parts and not self.parts[-1].endswith((" ", "\n")):
            self.parts.append(" ")

    def _break(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def text(self) -> str:
        text = re.sub(r"\n{2,}", "\n", "".join(self.parts))
        return "\n".join(line.strip() for line in text.splitlines()).strip()


@dataclass(frozen=True)
class PasswordInstructionContext:
    subject: str = ""
    body: str = ""
    sender: str = ""
    filename: str = ""


class PasswordInstructionExtractor:
    _instruction = re.compile(r"密碼|密码|password|パスワード|開啟碼|開啟密碼", re.IGNORECASE)
    _context_stop = re.compile(
        r"消費明細|消费明细|交易明細|交易明细|交易紀錄|交易记录|刷卡明細|刷卡明细|本期消費|本期消费|消費摘要|消费摘要|交易摘要",
        re.IGNORECASE,
    )
    _sensitive = re.compile(
        r"(?i)(?<![A-Z0-9])(?:[A-Z][12]\d{8}|(?:19|20)\d{6}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{3,}[-/.]\d{1,2}[-/.]\d{1,2}|\d{3,})(?![A-Z0-9])"
    )
    _email = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
    _assigned_literal = re.compile(
        r"(?i)(?:密碼|密码|password)\s*(?:是|為|为|is|[:：=])\s*([A-Za-z0-9!@#$%^&*._-]{4,})"
    )
    def extract(
        self,
        context: PasswordInstructionContext,
        sensitive_values: Iterable[str] = (),
    ) -> str:
        body = self._plain_text(context.body)
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        selected: list[str] = []
        if self._instruction.search(context.subject):
            selected.append(context.subject.strip())
        sender_name = context.sender.split("<", maxsplit=1)[0].strip().strip("\"'")
        if sender_name and self._instruction.search(sender_name):
            selected.append(sender_name)
        if self._instruction.search(context.filename):
            selected.append(context.filename.strip())

        selected_indexes: set[int] = set()
        for index, line in enumerate(lines):
            if not self._instruction.search(line):
                continue
            start = max(0, index - 1)
            end = min(len(lines), index + 5)
            for neighbor in range(start, end):
                if neighbor != index and self._context_stop.search(lines[neighbor]):
                    if neighbor < index:
                        continue
                    break
                selected_indexes.add(neighbor)
        selected.extend(lines[index] for index in sorted(selected_indexes))
        # Mask the complete selected context before applying the output cap.
        text = "\n".join(selected)
        for value in sensitive_values:
            if value and len(value) >= 4:
                text = text.replace(value, "[遮罩]")
        text = self._assigned_literal.sub("密碼說明：[遮罩]", text)
        text = self._email.sub("[寄件地址遮罩]", text)
        return self._sensitive.sub("[遮罩]", text)[:1200]

    @staticmethod
    def _plain_text(value: str) -> str:
        if not re.search(r"<\/?[A-Za-z][^>]*>|<br\s*/?>", value):
            return value.replace("\r\n", "\n").replace("\r", "\n")
        parser = _TextExtractor()
        try:
            parser.feed(value)
            return parser.text() if parser.parts else re.sub(r"<[^>]*>", " ", value)
        except Exception:
            return re.sub(r"<[^>]*>", " ", value)
