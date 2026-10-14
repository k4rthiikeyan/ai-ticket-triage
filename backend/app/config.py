from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field, AliasChoices


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=('.env', '.env.local'), extra='ignore', populate_by_name=True)
    admin_username: str = 'admin'
    admin_password: str = ''
    database_url: str = Field(default='sqlite:///./data/triage.db', validation_alias=AliasChoices('DATABASE_URL', 'POSTGRES_URL'))
    openrouter_api_key: SecretStr = SecretStr('')
    openrouter_embedding_api_key: SecretStr = SecretStr('')
    openrouter_base_url: str = 'https://openrouter.ai/api/v1'
    generation_model: str = 'openai/gpt-4.1-mini'
    embedding_model: str = 'openai/text-embedding-3-small'
    retrieval_threshold: float = Field(default=0.35, ge=0, le=1)
    inference_timeout: float = Field(default=60, gt=0, le=120)
    job_timeout: int = Field(default=240, ge=30, le=240)
    max_index_chunks: int = Field(default=256, ge=1, le=1000)
    auto_migrate: bool = True
    cookie_secure: bool = False
    session_hours: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()
