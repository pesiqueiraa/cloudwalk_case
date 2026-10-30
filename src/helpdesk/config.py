from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://helpdesk:helpdesk@localhost:55432/helpdesk"
    test_database_url: str = "postgresql://helpdesk:helpdesk@localhost:55432/helpdesk_test"
    kafka_bootstrap: str = "redpanda:9092"
    topic_inbound: str = "helpdesk.inbound"
    topic_outbound: str = "helpdesk.outbound"
    broker_url: str = "http://broker:8001"
    platform_url: str = "http://platform-web:8000"
    worker_poll_seconds: float = 0.5
    webhook_max_attempts: int = 10  # esperas 2+4+8+16+32+60x4 = ~5 min antes de desistir


@lru_cache
def get_settings() -> Settings:
    return Settings()
