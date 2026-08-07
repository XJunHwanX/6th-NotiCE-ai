from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from .push_repository import PushSubscriptionRepository


CATEGORY_MAP = {
    "academic": "학사",
    "graduation": "졸업",
    "research": "대학원/연구",
    "activity": "학생활동",
    "scholarship": "장학/근로",
    "contest": "대회/공모전",
    "career": "취업/인턴",
    "etc": "기타",
}


class InvalidCategoryError(ValueError):
    pass


class SubscriptionNotFoundError(LookupError):
    pass


class InvalidManagementTokenError(PermissionError):
    pass


@dataclass(frozen=True)
class RegisteredSubscription:
    subscription_id: str
    management_token: str
    created: bool


def hash_management_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_categories(category_ids: list[str]) -> list[str]:
    invalid = sorted(set(category_ids) - CATEGORY_MAP.keys())
    if invalid:
        raise InvalidCategoryError(
            f"지원하지 않는 카테고리입니다: {', '.join(invalid)}"
        )

    seen = set()
    normalized = []
    for category_id in category_ids:
        category = CATEGORY_MAP[category_id]
        if category not in seen:
            seen.add(category)
            normalized.append(category)
    return normalized


class PushSubscriptionService:
    def __init__(self, repository: PushSubscriptionRepository) -> None:
        self.repository = repository

    def register(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        category_ids: list[str],
    ) -> RegisteredSubscription:
        categories = normalize_categories(category_ids)
        management_token = secrets.token_urlsafe(32)
        values = {
            "endpoint": endpoint,
            "p256dh": p256dh,
            "auth": auth,
            "categories": categories,
            "management_token_hash": hash_management_token(management_token),
            "enabled": bool(categories),
        }
        existing = self.repository.find_by_endpoint(endpoint)

        if existing:
            row = self.repository.update(str(existing["id"]), values)
            created = False
        else:
            row = self.repository.insert(values)
            created = True

        return RegisteredSubscription(
            subscription_id=str(row["id"]),
            management_token=management_token,
            created=created,
        )

    def update_preferences(
        self,
        subscription_id: str,
        management_token: str,
        category_ids: list[str] | None,
        enabled: bool | None,
    ) -> dict:
        current = self._require_owned_subscription(
            subscription_id,
            management_token,
        )
        values = {}

        if category_ids is not None:
            values["categories"] = normalize_categories(category_ids)
            if enabled is None:
                values["enabled"] = bool(values["categories"])

        if enabled is not None:
            values["enabled"] = enabled

        if not values:
            return current
        return self.repository.update(subscription_id, values)

    def unsubscribe(
        self,
        subscription_id: str,
        management_token: str,
    ) -> None:
        self._require_owned_subscription(subscription_id, management_token)
        self.repository.delete(subscription_id)

    def _require_owned_subscription(
        self,
        subscription_id: str,
        management_token: str,
    ) -> dict:
        row = self.repository.fetch_by_id(subscription_id)
        if row is None:
            raise SubscriptionNotFoundError("푸시 구독을 찾지 못했습니다.")

        stored_hash = str(row.get("management_token_hash") or "")
        provided_hash = hash_management_token(management_token)
        if not hmac.compare_digest(stored_hash, provided_hash):
            raise InvalidManagementTokenError(
                "푸시 구독 관리 토큰이 올바르지 않습니다."
            )
        return row
