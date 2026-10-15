from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field, AliasChoices, field_validator

DEMO_USERNAME = 'demo'
DEMO_PASSWORD = 'try-triage'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=('.env', '.env.local'), extra='ignore', populate_by_name=True)
    admin_username: str = 'admin'
    admin_password: str = ''
    public_demo_enabled: bool = False
    customer_portal_enabled: bool = True
    database_url: str = Field(default='sqlite:///./data/triage.db', validation_alias=AliasChoices('DATABASE_URL', 'POSTGRES_URL'))
    openrouter_api_key: SecretStr = SecretStr('')
    openrouter_embedding_api_key: SecretStr = SecretStr('')
    openrouter_base_url: str = 'https://openrouter.ai/api/v1'
    generation_model: str = 'nvidia/nemotron-3-super-120b-a12b:free'
    embedding_model: str = 'nvidia/nemotron-3-embed-1b:free'
    retrieval_threshold: float = Field(default=0.35, ge=0, le=1)
    inference_timeout: float = Field(default=60, gt=0, le=120)
    job_timeout: int = Field(default=240, ge=30, le=240)
    max_index_chunks: int = Field(default=256, ge=1, le=1000)
    auto_migrate: bool = True
    cookie_secure: bool = False
    session_hours: int = 8
    demo_idle_minutes: int = Field(default=30, ge=5, le=120)
    ai_daily_limit: int = Field(default=40, ge=1, le=50)
    ai_minute_limit: int = Field(default=8, ge=1, le=20)
    demo_ai_daily_limit: int = Field(default=12, ge=1, le=40)
    demo_ticket_limit: int = Field(default=25, ge=1, le=100)
    demo_article_limit: int = Field(default=15, ge=2, le=100)

    @field_validator('admin_username')
    @classmethod
    def reserve_demo_username(cls, value):
        if value.casefold() == DEMO_USERNAME:
            raise ValueError('The demo username is reserved for public demo access. Choose another administrator username.')
        return value

    @field_validator('generation_model', 'embedding_model')
    @classmethod
    def only_free_models(cls, value):
        value = value.strip()
        if not value.endswith(':free') or '/' not in value:
            raise ValueError('This prototype only accepts OpenRouter model IDs ending in :free. Paid models are blocked.')
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
