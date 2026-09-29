from .openai_responses import OpenAIResponsesInterpreter


class GroqResponsesInterpreter(OpenAIResponsesInterpreter):
    """Groq's OpenAI-compatible Responses API without unsupported response storage."""

    endpoint = "https://api.groq.com/openai/v1/responses"
    provider_name = "Groq"
    include_store = False
