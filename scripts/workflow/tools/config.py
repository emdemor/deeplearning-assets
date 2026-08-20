from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional

class WebSearchConfig(BaseSettings):
    REGION: Optional[str] = None
    TIMEOUT: int = 10
    TIMELIMIT: Literal["d", "w", "m", "y"] | None = None
    BATCH_SIZE: int = 10
    MAX_CONCURRENCY: int = 3
    DELAY: float = 0.4
    MAX_RETRIES: int = 3
    RETRY_BASE_WAIT: int = 1
    RETRY_MAX_WAIT: int = 32

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_prefix="WEBSEARCH_",
        env_ignore_empty=True
    )


class WebFetchConfig(BaseSettings):
    MIN_CONTENT_LENGTH: int = 200
    MIN_WORD_COUNT: int = 50
    VALIDITY_THRESHOLD: float = -1.0
    WAYBACK_TIMEOUT: int = 30
    WAYBACK_MAX_RETRIES: int = 3
    WAYBACK_RETRY_BASE_WAIT: int = 3
    WAYBACK_RETRY_MAX_WAIT: int = 32
    WAYBACK_CDX_API: str = "https://web.archive.org/cdx/search/cdx"

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_prefix="WEBFETCH_",
        env_ignore_empty=True
    )

websearch_config = WebSearchConfig()
webfetch_config = WebFetchConfig()