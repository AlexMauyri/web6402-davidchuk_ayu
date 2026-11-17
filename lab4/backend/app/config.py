from pathlib import Path

from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(alias="POSTGRES_HOST")
    postgres_port: int = Field(alias="POSTGRES_PORT")
    postgres_db: str = Field(alias="POSTGRES_DB")
    session_secret_key: SecretStr | None = Field(default=None, alias="SESSION_SECRET_KEY")
    session_ttl: int = Field(default=1800, gt=0, alias="SESSION_TTL")
    cookie_secure: bool = Field(default=True, alias="COOKIE_SECURE")

    @property
    def postgres_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


settings = Settings()

