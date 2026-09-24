from uuid import uuid4

from sqlalchemy.orm import Session

from ...models import AIProviderProfile
from ..secrets.ports import SecretStore
from .openai_responses import OpenAIResponsesInterpreter
from .ports import PasswordRuleInterpreterUnavailable


class AIProviderService:
    def __init__(self, secret_store: SecretStore):
        self.secret_store = secret_store

    def configure(self, session: Session, api_key: str, model: str) -> AIProviderProfile:
        api_key = api_key.strip()
        model = model.strip()
        if not api_key or not model or len(model) > 120:
            raise ValueError("請提供 API key 與模型名稱")
        new_reference = f"ai-provider:{uuid4()}:api-key"
        old_reference = None
        try:
            with session.begin():
                profile = session.get(AIProviderProfile, "openai")
                old_reference = profile.api_key_credential_ref if profile else None
                self.secret_store.set(new_reference, api_key)
                if profile is None:
                    profile = AIProviderProfile(
                        id="openai",
                        provider="openai",
                        model=model,
                        api_key_credential_ref=new_reference,
                    )
                    session.add(profile)
                else:
                    profile.model = model
                    profile.api_key_credential_ref = new_reference
        except Exception:
            try:
                self.secret_store.delete(new_reference)
            except Exception:
                pass
            raise
        if old_reference:
            try:
                self.secret_store.delete(old_reference)
            except Exception:
                pass
        return profile

    def interpreter(self, session: Session) -> OpenAIResponsesInterpreter:
        profile = session.get(AIProviderProfile, "openai")
        api_key = self.secret_store.get(profile.api_key_credential_ref) if profile else None
        if profile is None or not api_key:
            raise PasswordRuleInterpreterUnavailable("尚未設定 AI provider")
        return OpenAIResponsesInterpreter(api_key, profile.model)
