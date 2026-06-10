from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    grpc_addr: str = "127.0.0.1:50052"
    lang: str = "es"
    max_batch: int = 32
    max_delay: float = 0.25
    max_workers: int = 4

    class Config:
        env_file = ".env"


settings = Settings()
