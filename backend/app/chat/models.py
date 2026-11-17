"""Chat model: OpenAI (via langchain-openai) or Google Gemini (via langchain-google-genai)."""
import os

from fastapi import HTTPException
from langchain_core.language_models import BaseChatModel


def get_chat_model() -> BaseChatModel:
    """Returns a LangChain chat model. Supports OpenAI, native Google Gemini, or custom OpenAI-compatible base_url."""
    openai_key = os.environ.get("OPENAI_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("HL_CHAT_MODEL")

    if openai_key or base_url:
        if not openai_key and not gemini_key:
            raise HTTPException(503, "Chat is not configured: set OPENAI_API_KEY or GEMINI_API_KEY")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model or "gpt-4o", api_key=openai_key or gemini_key, base_url=base_url, temperature=0)

    if gemini_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model or "gemini-3.5-flash-lite", google_api_key=gemini_key, temperature=0)

    raise HTTPException(503, "Chat is not configured: set OPENAI_API_KEY or GEMINI_API_KEY")
