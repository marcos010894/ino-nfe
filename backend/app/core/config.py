from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    cert_encryption_key: str
    
    acbr_api_client_id: str = ""
    acbr_api_client_secret: str = ""
    acbr_api_env: str = "homologacao"

    # SMTP — envio de XMLs pro contador (Central de Documentos v3).
    # Hostinger: smtp.hostinger.com:465 SSL. Senha vai em env `SMTP_PASSWORD`
    # do VPS docker-compose, nunca no repo. Vazio = envio ao contador desligado.
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "InnoFiscal"
    # Liga o cron que dispara envio no dia N do mês (per-empresa). Deixa off em
    # local/dev pra não mandar email por acidente.
    envio_contador_cron_ativo: bool = False

    class Config:
        env_file = ".env"

settings = Settings()
