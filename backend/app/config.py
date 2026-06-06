from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    phoenix_api_base_url: str = ""
    phoenix_api_token: str = ""
    ssh_private_key_path: str = "/keys/case1_key.pem"
    ssh_keys_dir: str = "/keys"
    ssh_username: str = "azureuser"
    ssh_connect_timeout: int = 25
    ssh_connect_retries: int = 3
    ssh_retry_delay_seconds: float = 2.0
    ssh_command_timeout: int = 120

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_publishable_key: str = ""

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-5.4-nano"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"

    # gemini | azure — which LLM drives command proposals and activity drafts
    llm_primary: str = "gemini"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    mock_mode: bool = False
    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
