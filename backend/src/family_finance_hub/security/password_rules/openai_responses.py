import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ports import PasswordRuleInterpreterUnavailable
from .schema import PasswordRule


class OpenAIResponsesInterpreter:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, model: str):
        if not api_key.strip() or not model.strip():
            raise ValueError("AI provider credentials and model are required")
        self.api_key = api_key
        self.model = model.strip()

    def interpret(self, instruction: str, context: dict[str, str]) -> PasswordRule:
        if not instruction.strip():
            raise PasswordRuleInterpreterUnavailable("No password instructions were found")
        schema = PasswordRule.model_json_schema()
        payload = {
            "model": self.model,
            "store": False,
            "input": [
                {
                    "role": "system",
                    "content": [{
                        "type": "input_text",
                        "text": (
                            "Convert the supplied password instructions into the allowed schema only. "
                            "Do not guess missing rules. Use status ambiguous for multiple explicit interpretations, "
                            "and unsupported when the instructions cannot be represented. Never output a password."
                        ),
                    }],
                },
                {
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": json.dumps({"instruction": instruction, "context": context}, ensure_ascii=False),
                    }],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "password_rule",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                result = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            raise PasswordRuleInterpreterUnavailable("AI 密碼規則服務目前無法使用") from None
        finally:
            del request

        output_text = self._output_text(result)
        if not output_text:
            raise PasswordRuleInterpreterUnavailable("AI 未提供可用的密碼規則")
        try:
            return PasswordRule.model_validate_json(output_text)
        except ValueError:
            raise PasswordRuleInterpreterUnavailable("AI 回傳的密碼規則不符合安全規格") from None

    @staticmethod
    def _output_text(response: dict) -> str:
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        return ""
