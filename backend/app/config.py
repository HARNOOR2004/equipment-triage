from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    openrouter_api_key: str = ""
    openrouter_model: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()