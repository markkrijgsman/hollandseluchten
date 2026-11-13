"""Chat model: OpenAI through LangChain. Swap the provider by returning another LangChain chat model."""
import os

from fastapi import HTTPException
from langchain_core.language_models import BaseChatModel


def get_chat_model() -> BaseChatModel:
    """OpenAI (HL_CHAT_MODEL, default gpt-4o). Without OPENAI_API_KEY /chat answers 503 instead of guessing."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(503, "Chat is not configured: set OPENAI_API_KEY")
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=os.environ.get("HL_CHAT_MODEL", "gpt-4o"), temperature=0)
