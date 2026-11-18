from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "VideshaMitra Backend"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:5174"]
    
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:54322/postgres"
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
