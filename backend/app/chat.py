from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from rag.src.chatbot import ChatbotService
from rag.src.db import ChunkRepositoryError, NoticeRepositoryError

from .dependencies import get_chatbot_service
from .schemas import ChatRequest, ChatResponse


router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    service: ChatbotService = Depends(get_chatbot_service),
) -> ChatResponse:
    try:
        result = service.handle_message(
            message=request.message,
            state_snapshot=(
                request.state.model_dump() if request.state is not None else None
            ),
        )
    except (ChunkRepositoryError, NoticeRepositoryError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    return ChatResponse(
        answer=result.answer,
        state=result.state,
        sources=result.sources,
    )
