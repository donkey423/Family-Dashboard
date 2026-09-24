from typing import Protocol

from .schema import PasswordRule


class PasswordRuleInterpreter(Protocol):
    def interpret(self, instruction: str, context: dict[str, str]) -> PasswordRule: ...


class PasswordRuleInterpreterUnavailable(Exception):
    pass
