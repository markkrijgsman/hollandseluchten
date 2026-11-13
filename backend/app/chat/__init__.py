"""Chat layer: question -> LLM tool calls -> answer with audit."""
from .engine import ChatRequest, chat
from .models import FakeChatModel, get_chat_model

__all__ = ["ChatRequest", "chat", "FakeChatModel", "get_chat_model"]
