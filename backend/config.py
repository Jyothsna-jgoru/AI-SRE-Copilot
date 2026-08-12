from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI SRE Copilot"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./.local/ai_sre.db"
    jwt_secret_key: str = "local-development-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    mcp_server_url: str = "http://localhost:8001/mcp"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8001
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_context_length: int = 8192
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "operations_knowledge"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    kafka_bootstrap_servers: str = "localhost:9092"
    auto_seed: bool = True
    demo_mode: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

