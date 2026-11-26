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
    classifier: str = "keyword"     # implementação da triagem: "keyword" roda sem chave; "jev" usa o TypeSafe
    typesafe_api_key: str = ""
    jev_model: str = "jev-1.14.0"   # versão fixada: os limiares da triagem foram medidos nela
    jev_timeout_seconds: float = 1.0  # passou disso, a triagem cai nas regras (e audita o motivo)
    agent_impl: str = "mock"        # agente: "mock" determinístico ou "llm" (Claude)
    anthropic_api_key: str = ""
    agent_llm_model: str = "claude-sonnet-5-5"
    agent_llm_effort: str = "low"
    agent_llm_timeout_seconds: float = 30.0
    cors_origins: list[str] = ["http://localhost:5173"]  # telas em React; só elas chamam a API pelo navegador


@lru_cache
def get_settings() -> Settings:
    return Settings()
