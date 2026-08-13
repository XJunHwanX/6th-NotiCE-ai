from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


CategoryId = Literal[
    "academic",
    "graduation",
    "research",
    "activity",
    "scholarship",
    "contest",
    "career",
    "etc",
]


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=512)
    auth: str = Field(min_length=1, max_length=512)


class BrowserPushSubscription(BaseModel):
    endpoint: HttpUrl
    keys: PushKeys


class PushSubscriptionCreate(BaseModel):
    subscription: BrowserPushSubscription
    categories: list[CategoryId] = Field(default_factory=list, max_length=8)


class PushSubscriptionUpdate(BaseModel):
    categories: list[CategoryId] | None = Field(default=None, max_length=8)
    enabled: bool | None = None


class PushSubscriptionResponse(BaseModel):
    subscriptionId: str
    managementToken: str
    created: bool


class PushSubscriptionUpdateResponse(BaseModel):
    subscriptionId: str
    categories: list[str]
    enabled: bool


class VapidPublicKeyResponse(BaseModel):
    publicKey: str


class ChatStatePayload(BaseModel):
    last_search_query: str | None = Field(default=None, max_length=1000)
    referenced_notice_ids: list[int | str] = Field(
        default_factory=list,
        max_length=100,
    )
    shown_notice_ids: list[int | str] = Field(
        default_factory=list,
        max_length=100,
    )
    candidate_notice_ids: list[int | str] = Field(
        default_factory=list,
        max_length=100,
    )
    active_notice_id: int | str | None = None
    pending_answer_question: str | None = Field(default=None, max_length=1000)
    router_context: list[dict[str, str]] = Field(
        default_factory=list,
        max_length=6,
    )


class ChatRequest(BaseModel):
    action: Literal["message", "select_notice", "load_more"] = "message"
    message: str = Field(default="", max_length=1000)
    selected_notice_id: int | str | None = None
    state: ChatStatePayload | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> "ChatRequest":
        if self.action == "message" and not self.message.strip():
            raise ValueError("message 액션에는 질문이 필요합니다.")
        if self.action == "select_notice" and self.selected_notice_id is None:
            raise ValueError(
                "select_notice 액션에는 selected_notice_id가 필요합니다."
            )
        if self.action == "load_more" and self.state is None:
            raise ValueError("load_more 액션에는 기존 대화 상태가 필요합니다.")
        return self


class ChatSource(BaseModel):
    id: int | str | None
    title: str
    publishedAt: str | None = None
    url: str | None = None


class ChatResponse(BaseModel):
    answer: str
    state: ChatStatePayload
    sources: list[ChatSource]
    selectionRequired: bool = False
    hasMore: bool = False
