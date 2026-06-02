from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    llama_url: str = "http://127.0.0.1:8081"
    callback_url: str | None = None
    grpc_addr: str = "127.0.0.1:50051"
    
    class Config:
        env_file = ".env"

settings = Settings()