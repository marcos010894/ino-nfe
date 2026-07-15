import os
import shutil
from datetime import datetime
from fastapi import UploadFile, HTTPException
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend

STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage", "certificados")

def save_certificado_file(empresa_id: int, file: UploadFile) -> str:
    """Salva o arquivo .pfx de forma segura na pasta privada."""
    os.makedirs(STORAGE_DIR, exist_ok=True)
    filename = f"cert_{empresa_id}_{file.filename}"
    file_path = os.path.join(STORAGE_DIR, filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return file_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo: {str(e)}")

def get_certificado_validade(file_path: str, password: str) -> datetime:
    """Lê o arquivo .pfx e retorna a data de expiração (not_valid_after)."""
    try:
        with open(file_path, "rb") as f:
            pfx_data = f.read()
        
        # A biblioteca cryptography espera a senha em bytes
        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
            pfx_data, 
            password.encode(),
            backend=default_backend()
        )
        
        if not certificate:
            raise HTTPException(status_code=400, detail="Certificado inválido ou corrompido.")
            
        return certificate.not_valid_after
    except ValueError as e:
        # Erro de senha geralmente lança ValueError
        raise HTTPException(status_code=400, detail="Senha do certificado incorreta.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler certificado: {str(e)}")
