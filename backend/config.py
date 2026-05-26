import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://pharma_user:pharma_pass@localhost:5432/pharma_data"
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "pharma-data-integrity"
    LANGSMITH_TRACING: bool = True
    LANGSMITH_ENDPOINT: str = "https://eu.api.smith.langchain.com"
    OLLAMA_CLOUD_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "https://ollama.cloud/v1"
    OLLAMA_MODEL: str = "qwen3.5:397b"
    OPENAI_API_KEY: str = ""
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", "8000"))

    class Config:
        env_file = ".env"

settings = Settings()
