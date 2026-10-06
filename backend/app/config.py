from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()