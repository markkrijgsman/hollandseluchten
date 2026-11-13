"""Chat layer: question -> LLM tool calls -> answer with audit."""
from .engine import ChatRequest, chat
from .models import get_chat_model

__all__ = ["ChatRequest", "chat", "get_chat_model"]
