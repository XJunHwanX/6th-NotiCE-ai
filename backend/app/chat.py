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
            selected_notice_id=(
                request.selected_notice_id
                if request.action == "select_notice"
                else None
            ),
            load_more=request.action == "load_more",
            candidate_page=(request.page if request.action == "page" else None),
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
        selectionRequired=result.selection_required,
        hasMore=result.has_more,
        page=result.page,
        pageCount=result.page_count,
    )
