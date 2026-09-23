"""Central configuration. All tunables live here or in the environment."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="IS_", extra="ignore")

    # --- Storage ---
    postgres_url: str = "postgresql://is_sarthi:is_sarthi@localhost:5432/is_standards"
    redis_url: str = "redis://localhost:6379/0"
    neo4j_url: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "is_standards"

    # --- Models ---
    embedding_model: str = "intfloat/multilingual-e5-base"
    reranker_model: str = "BAAI/bge-reranker-base"
    llm_provider: str = "stub"  # anthropic | openai | local | stub
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key: str = ""
    local_llm_url: str = "http://localhost:11434/api/generate"

    # --- Crawling politeness ---
    crawl_delay_seconds: float = 1.5
    request_timeout: int = 20
    max_retries: int = 3
    user_agent: str = (
        "IS-Sarthi/1.0 (SIH2026 academic research; contact: team@example.edu)"
    )
    circuit_breaker_threshold: int = 10
    raw_snapshot_dir: str = "data/raw_snapshots"

    # --- Retrieval tuning ---
    dense_top_k: int = 50
    sparse_top_k: int = 50
    rrf_k: int = 60
    rerank_top_k: int = 10
    final_top_k: int = 5
    graph_depth: int = 2
    min_confidence: float = 0.35

    # --- Schedules ---
    full_sync_hour: int = 2
    delta_sync_hour: int = 6
    gazette_hour: int = 8


settings = Settings()
