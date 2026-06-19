from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    grpc_addr: str = "127.0.0.1:50052"
    # Evita el nombre 'lang': colisiona con la env var estándar LANG (C.UTF-8).
    analyzer_lang: str = "es"
    max_batch: int = 32
    max_delay: float = 0.25
    max_workers: int = 4

    # Análisis de imágenes con Gemini
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-2.5-flash-lite"
    http_timeout: float = 15.0

    # S3 vía boto3 (desactivado por ahora).
    # aws_region: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()
