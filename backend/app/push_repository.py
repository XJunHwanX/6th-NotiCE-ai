from __future__ import annotations

from typing import Protocol

import requests


class PushSubscriptionRepositoryError(RuntimeError):
    """Raised when the push subscription store cannot be accessed."""


class PushSubscriptionRepository(Protocol):
    def find_by_endpoint(self, endpoint: str) -> dict | None: ...

    def fetch_by_id(self, subscription_id: str) -> dict | None: ...

    def insert(self, values: dict) -> dict: ...

    def update(self, subscription_id: str, values: dict) -> dict: ...

    def delete(self, subscription_id: str) -> None: ...


class SupabasePushSubscriptionRepository:
    TABLE_NAME = "push_subscriptions"

    def __init__(
        self,
        url: str,
        service_role_key: str,
        session: requests.Session | None = None,
    ) -> None:
        if not url or not service_role_key:
            raise PushSubscriptionRepositoryError(
                "SUPABASE_URL 또는 SUPABASE_SERVICE_ROLE_KEY가 없습니다."
            )

        self.url = url.rstrip("/")
        self.service_role_key = service_role_key
        self.session = session or requests.Session()

    @property
    def table_url(self) -> str:
        return f"{self.url}/rest/v1/{self.TABLE_NAME}"

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.service_role_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.service_role_key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.service_role_key}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    @staticmethod
    def _first_row(response: requests.Response) -> dict | None:
        rows = response.json()
        if not isinstance(rows, list):
            raise PushSubscriptionRepositoryError(
                "Supabase 구독 응답이 배열 형태가 아닙니다."
            )
        return rows[0] if rows else None

    def find_by_endpoint(self, endpoint: str) -> dict | None:
        try:
            response = self.session.get(
                self.table_url,
                headers=self._headers(),
                params={
                    "select": "*",
                    "endpoint": f"eq.{endpoint}",
                    "limit": 1,
                },
                timeout=20,
            )
            response.raise_for_status()
            return self._first_row(response)
        except (requests.RequestException, ValueError) as error:
            raise PushSubscriptionRepositoryError(
                f"푸시 구독 조회에 실패했습니다: {error}"
            ) from error

    def fetch_by_id(self, subscription_id: str) -> dict | None:
        try:
            response = self.session.get(
                self.table_url,
                headers=self._headers(),
                params={
                    "select": "*",
                    "id": f"eq.{subscription_id}",
                    "limit": 1,
                },
                timeout=20,
            )
            response.raise_for_status()
            return self._first_row(response)
        except (requests.RequestException, ValueError) as error:
            raise PushSubscriptionRepositoryError(
                f"푸시 구독 조회에 실패했습니다: {error}"
            ) from error

    def insert(self, values: dict) -> dict:
        try:
            response = self.session.post(
                self.table_url,
                headers=self._headers("return=representation"),
                json=values,
                timeout=20,
            )
            response.raise_for_status()
            row = self._first_row(response)
        except (requests.RequestException, ValueError) as error:
            raise PushSubscriptionRepositoryError(
                f"푸시 구독 저장에 실패했습니다: {error}"
            ) from error

        if row is None:
            raise PushSubscriptionRepositoryError(
                "푸시 구독 저장 결과가 비어 있습니다."
            )
        return row

    def update(self, subscription_id: str, values: dict) -> dict:
        try:
            response = self.session.patch(
                self.table_url,
                headers=self._headers("return=representation"),
                params={"id": f"eq.{subscription_id}"},
                json=values,
                timeout=20,
            )
            response.raise_for_status()
            row = self._first_row(response)
        except (requests.RequestException, ValueError) as error:
            raise PushSubscriptionRepositoryError(
                f"푸시 구독 수정에 실패했습니다: {error}"
            ) from error

        if row is None:
            raise PushSubscriptionRepositoryError(
                "수정할 푸시 구독을 찾지 못했습니다."
            )
        return row

    def delete(self, subscription_id: str) -> None:
        try:
            response = self.session.delete(
                self.table_url,
                headers=self._headers(),
                params={"id": f"eq.{subscription_id}"},
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise PushSubscriptionRepositoryError(
                f"푸시 구독 해지에 실패했습니다: {error}"
            ) from error
