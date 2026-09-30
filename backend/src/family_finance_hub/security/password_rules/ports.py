from typing import Protocol

from .schema import PasswordRule


class PasswordRuleInterpreter(Protocol):
    def interpret(self, instruction: str, context: dict[str, str]) -> PasswordRule: ...


class PasswordRuleInterpreterUnavailable(Exception):
    def __init__(self, message: str, reason_code: str = "ai_service_unavailable"):
        super().__init__(message)
        self.reason_code = reason_code
