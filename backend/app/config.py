from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"   
    cors_origins: str = "http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()