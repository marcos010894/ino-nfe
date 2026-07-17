from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    cert_encryption_key: str
    
    acbr_api_client_id: str = ""
    acbr_api_client_secret: str = ""
    acbr_api_env: str = "homologacao"

    class Config:
        env_file = ".env"

settings = Settings()
