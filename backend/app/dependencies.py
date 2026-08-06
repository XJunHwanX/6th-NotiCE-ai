from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException, status

from .config import get_settings
from .push_repository import SupabasePushSubscriptionRepository
from .push_service import PushSubscriptionService


@lru_cache(maxsize=1)
def _create_push_service() -> PushSubscriptionService:
    settings = get_settings()
    repository = SupabasePushSubscriptionRepository(
        url=settings.supabase_url,
        service_role_key=settings.supabase_service_role_key,
    )
    return PushSubscriptionService(repository)


def get_push_service() -> PushSubscriptionService:
    try:
        return _create_push_service()
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@lru_cache(maxsize=1)
def _create_chatbot_service():
    from rag.src.chatbot import ChatbotService

    return ChatbotService.create_default()


def get_chatbot_service():
    from rag.src.chatbot import ChatbotConfigurationError

    try:
        return _create_chatbot_service()
    except ChatbotConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
