import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ports import PasswordRuleInterpreterUnavailable
from .schema import PasswordRule


class OpenAIResponsesInterpreter:
    endpoint = "https://api.openai.com/v1/responses"
    provider_name = "OpenAI"
    include_store = True

    def __init__(self, api_key: str, model: str):
        if not api_key.strip() or not model.strip():
            raise ValueError("AI provider credentials and model are required")
        self.api_key = api_key
        self.model = model.strip()

    def interpret(self, instruction: str, context: dict[str, str]) -> PasswordRule:
        if not instruction.strip():
            raise PasswordRuleInterpreterUnavailable(
                "No password instructions were found",
                "ai_schema_invalid",
            )
        schema = PasswordRule.model_json_schema()
        payload = {
            "model": self.model,
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
        if self.include_store:
            payload["store"] = False
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                response_body = response.read()
        except HTTPError as error:
            if error.code == 429:
                try:
                    error_code = json.loads(error.read(32_768)).get("error", {}).get("code")
                except (ValueError, OSError, AttributeError):
                    error_code = None
                if error_code in {
                    "insufficient_quota",
                    "credit_balance_exhausted",
                    "organization_spend_limit_exceeded",
                    "project_spend_limit_exceeded",
                    "organization_usage_limit_exceeded",
                }:
                    raise PasswordRuleInterpreterUnavailable(
                        f"{self.provider_name} API 額度不足，請檢查 API 帳戶的用量設定",
                        "ai_quota_unavailable",
                    ) from None
                if error_code in {"rate_limit_exceeded", "slow_down"}:
                    raise PasswordRuleInterpreterUnavailable(
                        "AI 請求過於頻繁，請稍後再試",
                        "ai_rate_limited",
                    ) from None
                raise PasswordRuleInterpreterUnavailable(
                    "AI API 回應 429，請檢查額度與速率限制",
                    "ai_rate_limited",
                ) from None
            messages = {
                400: f"{self.provider_name} 請求格式不被目前模型接受，請檢查模型設定",
                401: f"{self.provider_name} API key 無效，請在設定重新儲存",
                403: f"{self.provider_name} API key 沒有使用此模型的權限",
                404: f"{self.provider_name} 找不到指定模型，請檢查模型設定",
            }
            reason_codes = {
                400: "ai_model_unavailable",
                401: "ai_auth_failed",
                403: "ai_model_unavailable",
                404: "ai_model_unavailable",
            }
            raise PasswordRuleInterpreterUnavailable(
                messages.get(error.code, "AI 密碼規則服務目前無法使用"),
                reason_codes.get(error.code, "ai_service_unavailable"),
            ) from None
        except TimeoutError:
            raise PasswordRuleInterpreterUnavailable(
                "AI 密碼規則服務回應逾時",
                "ai_timeout",
            ) from None
        except URLError as error:
            reason_code = "ai_timeout" if isinstance(error.reason, TimeoutError) else "ai_service_unavailable"
            message = "AI 密碼規則服務回應逾時" if reason_code == "ai_timeout" else "AI 密碼規則服務目前無法使用"
            raise PasswordRuleInterpreterUnavailable(message, reason_code) from None
        except OSError:
            raise PasswordRuleInterpreterUnavailable(
                "AI 密碼規則服務目前無法使用",
                "ai_service_unavailable",
            ) from None
        finally:
            del request

        try:
            result = json.loads(response_body)
        except (TypeError, ValueError):
            raise PasswordRuleInterpreterUnavailable(
                "AI 回傳內容無法解析",
                "ai_schema_invalid",
            ) from None

        output_text = self._output_text(result)
        if not output_text:
            raise PasswordRuleInterpreterUnavailable(
                "AI 未提供可用的密碼規則",
                "ai_schema_invalid",
            )
        try:
            return PasswordRule.model_validate_json(output_text)
        except ValueError:
            raise PasswordRuleInterpreterUnavailable(
                "AI 回傳的密碼規則不符合安全規格",
                "ai_schema_invalid",
            ) from None

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
