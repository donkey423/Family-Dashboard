from dataclasses import dataclass
from html.parser import HTMLParser
import re
from collections.abc import Iterable


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


@dataclass(frozen=True)
class PasswordInstructionContext:
    subject: str = ""
    body: str = ""
    sender: str = ""
    filename: str = ""


class PasswordInstructionExtractor:
    _instruction = re.compile(r"密碼|密码|password|パスワード|開啟碼|開啟密碼", re.IGNORECASE)
    _sensitive = re.compile(
        r"(?i)(?:\b[A-Z][12]\d{8}\b|\b(?:19|20)\d{6}\b|\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b|\b\d{3,}\b)"
    )
    _email = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
    _assigned_literal = re.compile(
        r"(?i)(?:密碼|密码|password)\s*(?:是|為|为|is|[:：=])\s*([A-Za-z0-9!@#$%^&*._-]{6,})"
    )
    _assignment_explanation = re.compile(
        r"(?i)身分|身份|生日|出生|年月日|前|後|后|末|first|last|birthday|identity|id|format|格式"
    )

    def extract(
        self,
        context: PasswordInstructionContext,
        sensitive_values: Iterable[str] = (),
    ) -> str:
        body = self._plain_text(context.body)
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        selected = []
        if self._instruction.search(context.subject):
            selected.append(context.subject.strip())
        sender_name = context.sender.split("<", maxsplit=1)[0].strip().strip("\"'")
        if sender_name and self._instruction.search(sender_name):
            selected.append(sender_name)
        if self._instruction.search(context.filename):
            selected.append(context.filename.strip())
        selected.extend(line for line in lines if self._instruction.search(line))
        text = "\n".join(dict.fromkeys(selected))[:1600]
        for value in sensitive_values:
            if value and len(value) >= 4:
                text = text.replace(value, "[遮罩]")
        text = self._assigned_literal.sub(
            lambda match: match.group(0) if self._assignment_explanation.search(match.group(1)) else "密碼說明：[遮罩]",
            text,
        )
        text = self._email.sub("[寄件地址遮罩]", text)
        return self._sensitive.sub("[遮罩]", text)[:1200]

    @staticmethod
    def _plain_text(value: str) -> str:
        parser = _TextExtractor()
        try:
            parser.feed(value)
            return "\n".join(parser.parts) if parser.parts else re.sub(r"<[^>]*>", " ", value)
        except Exception:
            return re.sub(r"<[^>]*>", " ", value)
