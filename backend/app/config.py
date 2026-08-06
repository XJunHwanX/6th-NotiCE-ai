from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]


def _split_origins(raw_origins: str) -> tuple[str, ...]:
    return tuple(
        origin.strip().rstrip("/")
        for origin in raw_origins.split(",")
        if origin.strip()
    )


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    cors_origins: tuple[str, ...]
    supabase_url: str
    supabase_service_role_key: str
    vapid_public_key: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR / "backend" / ".env")
    load_dotenv(ROOT_DIR / "pipeline" / ".env")

    return Settings(
        app_name=os.getenv("APP_NAME", "NotiCE API"),
        environment=os.getenv("APP_ENV", "development"),
        cors_origins=_split_origins(
            os.getenv(
                "CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            )
        ),
        supabase_url=os.getenv("SUPABASE_URL", "").rstrip("/"),
        supabase_service_role_key=os.getenv(
            "SUPABASE_SERVICE_ROLE_KEY",
            "",
        ),
        vapid_public_key=os.getenv("VAPID_PUBLIC_KEY", ""),
    )
