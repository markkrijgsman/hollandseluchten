"""Chat model: OpenAI or OpenAI-compatible (e.g. Gemini via Google AI Studio) through LangChain."""
import os

from fastapi import HTTPException
from langchain_core.language_models import BaseChatModel


def get_chat_model() -> BaseChatModel:
    """Returns a LangChain chat model. Supports OpenAI, Gemini (via OpenAI-compatible endpoint), or custom base_url."""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    api_key = openai_key or gemini_key
    if not api_key:
        raise HTTPException(503, "Chat is not configured: set OPENAI_API_KEY or GEMINI_API_KEY")

    base_url = os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("HL_CHAT_MODEL")

    if gemini_key and not openai_key and not base_url:
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        if not model:
            model = "gemini-3.5-flash-lite"

    if not model:
        model = "gpt-4o"

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=0)

