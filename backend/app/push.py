from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from .config import Settings, get_settings
from .dependencies import get_push_service
from .push_repository import PushSubscriptionRepositoryError
from .push_service import (
    InvalidCategoryError,
    InvalidManagementTokenError,
    PushSubscriptionService,
    SubscriptionNotFoundError,
)
from .schemas import (
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    PushSubscriptionUpdate,
    PushSubscriptionUpdateResponse,
    VapidPublicKeyResponse,
)


router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
def get_vapid_public_key(
    settings: Settings = Depends(get_settings),
) -> VapidPublicKeyResponse:
    if not settings.vapid_public_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID_PUBLIC_KEY가 설정되지 않았습니다.",
        )
    return VapidPublicKeyResponse(publicKey=settings.vapid_public_key)


@router.post(
    "/subscriptions",
    response_model=PushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_push_subscription(
    request: PushSubscriptionCreate,
    response: Response,
    service: PushSubscriptionService = Depends(get_push_service),
) -> PushSubscriptionResponse:
    try:
        result = service.register(
            endpoint=str(request.subscription.endpoint),
            p256dh=request.subscription.keys.p256dh,
            auth=request.subscription.keys.auth,
            category_ids=list(request.categories),
        )
    except InvalidCategoryError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except PushSubscriptionRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if not result.created:
        response.status_code = status.HTTP_200_OK

    return PushSubscriptionResponse(
        subscriptionId=result.subscription_id,
        managementToken=result.management_token,
        created=result.created,
    )


@router.patch(
    "/subscriptions/{subscription_id}",
    response_model=PushSubscriptionUpdateResponse,
)
def update_push_subscription(
    subscription_id: str,
    request: PushSubscriptionUpdate,
    management_token: str = Header(alias="X-Subscription-Token"),
    service: PushSubscriptionService = Depends(get_push_service),
) -> PushSubscriptionUpdateResponse:
    try:
        row = service.update_preferences(
            subscription_id=subscription_id,
            management_token=management_token,
            category_ids=(
                list(request.categories)
                if request.categories is not None
                else None
            ),
            enabled=request.enabled,
        )
    except SubscriptionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidManagementTokenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except InvalidCategoryError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except PushSubscriptionRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return PushSubscriptionUpdateResponse(
        subscriptionId=str(row["id"]),
        categories=list(row.get("categories") or []),
        enabled=bool(row.get("enabled")),
    )


@router.delete(
    "/subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_push_subscription(
    subscription_id: str,
    management_token: str = Header(alias="X-Subscription-Token"),
    service: PushSubscriptionService = Depends(get_push_service),
) -> Response:
    try:
        service.unsubscribe(subscription_id, management_token)
    except SubscriptionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidManagementTokenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except PushSubscriptionRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
