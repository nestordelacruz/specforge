from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Default targets the docker-compose Postgres service. Override with
    # DATABASE_URL=sqlite:///./dev.db for a quick local / test run.
    database_url: str = "postgresql+psycopg2://specforge:specforge@db:5432/specforge"

    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


settings = Settings()
