import base64
import os
from datetime import datetime
from fastapi import UploadFile, HTTPException
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

UPLOAD_DIR = "uploads/certificados"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_certificado_file(empresa_id: int, file: UploadFile) -> str:
    """Salva o arquivo físico temporário/persistente."""
    if not file.filename.endswith(('.pfx', '.p12')):
        raise HTTPException(status_code=400, detail="O arquivo deve ser um .pfx ou .p12")
        
    file_path = os.path.join(UPLOAD_DIR, f"cert_empresa_{empresa_id}.pfx")
    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())
    return file_path

def parse_certificado(file_path: str, senha: str) -> dict:
    """Lê o .pfx/.p12 usando a senha e extrai os metadados."""
    try:
        with open(file_path, "rb") as f:
            pfx_data = f.read()
            
        # O cryptography espera a senha em bytes (no p12)
        password_bytes = senha.encode('utf-8')
        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
            pfx_data,
            password_bytes
        )
        
        if not certificate:
            raise HTTPException(status_code=400, detail="Nenhum certificado válido encontrado no arquivo.")
            
        # Extrair Informações
        not_valid_after = certificate.not_valid_after
        
        # Emissor
        issuer_list = certificate.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
        emissor = issuer_list[0].value if issuer_list else str(certificate.issuer)
        
        # Titular/Sujeito
        subject_list = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        sujeito = subject_list[0].value if subject_list else str(certificate.subject)
        
        return {
            "vencimento": not_valid_after,
            "emissor": emissor,
            "sujeito": sujeito,
            "base64": base64.b64encode(pfx_data).decode('utf-8')
        }
        
    except ValueError as e:
        # Erro de senha incorreta ou arquivo corrompido
        raise HTTPException(status_code=400, detail="Senha incorreta ou arquivo inválido.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar o certificado: {str(e)}")
