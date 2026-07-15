import base64
from cryptography.fernet import Fernet
from app.core.config import settings

# A chave no .env deve ter 32 url-safe base64-encoded bytes.
# Se o tamanho não estiver correto, o Fernet não funciona.
# Vamos criar um handler robusto:
def _get_fernet_key():
    key = settings.cert_encryption_key
    # Se a chave não for válida para o Fernet (ex: "outra-chave-aleatoria-para-certificado"),
    # vamos derivar uma chave de 32 bytes válida.
    if len(key) != 44 or not key.endswith("="):
        # Derivação de chave simplificada para não quebrar o .env atual
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"inno_salt",
            iterations=100000,
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(key.encode()))
        return derived_key
    return key.encode()

_fernet = Fernet(_get_fernet_key())

def encrypt_data(data: str) -> str:
    if not data:
        return data
    return _fernet.encrypt(data.encode()).decode()

def decrypt_data(token: str) -> str:
    if not token:
        return token
    return _fernet.decrypt(token.encode()).decode()
