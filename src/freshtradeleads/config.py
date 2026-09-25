from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def database_url() -> str:
    return os.getenv(
        "FRESHTRADELEADS_DATABASE_URL",
        "postgresql+psycopg:///freshtradeleads",
    )


def data_dir() -> Path:
    return Path(os.getenv("FRESHTRADELEADS_DATA_DIR", "/opt/freshtradeleads/data"))


@dataclass(frozen=True)
class WebSettings:
    database_url: str
    data_dir: Path
    base_url: str
    session_secret: str
    stripe_secret_key: str | None
    stripe_webhook_secret: str | None
    download_days: int = 7
    stripe_prices: dict[str, str] | None = None
    stripe_use_cli: bool = False
    secure_cookies: bool = False
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    promotion_code: str | None = None
    stripe_promotion_id: str | None = None
    promotion_percent: int = 20
    meta_pixel_id: str | None = None

    @property
    def stripe_ready(self) -> bool:
        supported_key_prefixes = ("sk_test_", "sk_live_", "rk_test_", "rk_live_")
        credential_ready = self.stripe_use_cli or bool(
            self.stripe_secret_key and self.stripe_secret_key.startswith(supported_key_prefixes)
        )
        return bool(credential_ready and self.stripe_webhook_secret and self.stripe_webhook_secret.startswith("whsec_") and self.stripe_prices and all(self.stripe_prices.get(k, "").startswith("price_") for k in ("starter","fresh-pack","expanded")))


def web_settings() -> WebSettings:
    prices={"starter":os.getenv("STRIPE_PRICE_STARTER", ""),"fresh-pack":os.getenv("STRIPE_PRICE_FRESH_PACK", ""),"expanded":os.getenv("STRIPE_PRICE_EXPANDED", "")}
    use_cli=os.getenv("STRIPE_USE_CLI","").lower() in {"1","true","yes"}
    secure=os.getenv("FRESHTRADELEADS_SECURE_COOKIES","").lower() in {"1","true","yes"}
    hosts=tuple(x.strip() for x in os.getenv("FRESHTRADELEADS_ALLOWED_HOSTS","localhost,127.0.0.1,testserver").split(",") if x.strip())
    return WebSettings(database_url(),data_dir(),os.getenv("FRESHTRADELEADS_BASE_URL","http://127.0.0.1:8080").rstrip("/"),os.getenv("FRESHTRADELEADS_SESSION_SECRET","development-only-change-me"),os.getenv("STRIPE_SECRET_KEY") or None,os.getenv("STRIPE_WEBHOOK_SECRET") or None,int(os.getenv("FRESHTRADELEADS_DOWNLOAD_DAYS","7")),prices,use_cli,secure,hosts,os.getenv("FRESHTRADELEADS_PROMOTION_CODE") or None,os.getenv("STRIPE_PROMOTION_CODE_ID") or None,int(os.getenv("FRESHTRADELEADS_PROMOTION_PERCENT","20")),os.getenv("META_PIXEL_ID") or None)
