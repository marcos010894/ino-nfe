import asyncio
import json
from sqlmodel import Session, select
from app.models.database import engine
from app.models.empresa import Empresa
from app.models.regra_fiscal import RegraFiscal
from app.services.acbr_api import ACBrAPIService

async def run_test():
    print("Iniciando teste de emissão de NFC-e...")
    
    with Session(engine) as session:
        # Buscar a empresa seedada
        empresa = session.exec(select(Empresa).where(Empresa.cnpj == "15278447000102")).first()
        if not empresa:
            print("Erro: Empresa INNOBYTE LTDA não encontrada no banco.")
            return
            
        # Buscar a regra fiscal da empresa
        regra = session.exec(select(RegraFiscal).where(RegraFiscal.empresa_id == empresa.id)).first()
        if not regra:
            print("Erro: Regra fiscal não cadastrada para a empresa.")
            return

        print(f"Empresa: {empresa.razao_social} (ID: {empresa.id})")
        print(f"Regra Fiscal: {regra.nome} (CFOP: {regra.cfop})")

        # Mock de JSON de venda do InnoSystem
        venda_data = {
            "cliente": {
                "nome": "Consumidor Final de Testes",
                "cpf": "99999999999"
            },
            "itens": [
                {
                    "codigo": "TESTE001",
                    "nome": "Colar Solitário Prata 925",
                    "quantidade": 1,
                    "valor_unitario": 120.00,
                    "unidade": "UN"
                }
            ],
            "desconto": 10.00,
            "pagamentos": [
                {
                    "meio_pagamento": "17",  # Pix
                    "valor": 110.00
                }
            ]
        }

        # Instanciar serviço
        acbr_service = ACBrAPIService()
        
        # Montar Payload
        print("Montando payload...")
        payload = acbr_service.montar_payload_nfce(empresa, regra, venda_data)
        print("Payload montado:")
        print(json.dumps(payload, indent=2))

        # Transmitir
        print("Transmitindo para ACBr API (Homologação)...")
        status, resposta = await acbr_service.transmitir_nfce(payload)
        
        print("\n=== RESULTADO DA TRANSMISSÃO ===")
        print(f"STATUS: {status.upper()}")
        print("RESPOSTA DA API:")
        print(json.dumps(resposta, indent=2))

if __name__ == "__main__":
    asyncio.run(run_test())
