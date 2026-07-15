from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    cert_encryption_key: str

    class Config:
        env_file = ".env"

settings = Settings()
