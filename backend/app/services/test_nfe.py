import asyncio
import json
from sqlmodel import Session, select
from app.models.database import engine
from app.models.empresa import Empresa
from app.models.regra_fiscal import RegraFiscal
from app.models.nota import Nota
from app.services.acbr_api import ACBrAPIService

async def test_nfe_flow():
    print("Iniciando teste de emissão assíncrona de NF-e (Modelo 55)...")
    
    with Session(engine) as session:
        # Carrega empresa Playcell
        empresa = session.exec(
            select(Empresa).where(Empresa.cnpj == "15278447000102")
        ).first()
        
        if not empresa:
            print("Empresa de testes não encontrada. Por favor execute seed_company primeiro.")
            return
            
        regra = session.exec(
            select(RegraFiscal).where(RegraFiscal.empresa_id == empresa.id)
        ).first()
        
        venda_data = {
            "itens": [
                {
                    "codigo": "TESTE002",
                    "nome": "COLAR DE OURO 18K",
                    "quantidade": 1.0,
                    "valor_unitario": 850.00
                }
            ],
            "desconto": 50.00,
            "pagamentos": [
                {
                    "meio_pagamento": "17", # Pix
                    "valor": 800.00
                }
            ],
            "cliente": {
                "nome": "Adquirente de Joias Teste",
                "cpf": "11122233344"
            }
        }
        
        # 1. Montar payload
        acbr_service = ACBrAPIService()
        payload = acbr_service.montar_payload_nfce(empresa, regra, venda_data, modelo=55)
        print("Payload gerado para Modelo 55 (NF-e):")
        print(json.dumps(payload, indent=2))
        
        # 2. Transmitir NF-e
        print("\nTransmitindo para a integradora (Fila assíncrona)...")
        status, resposta = await acbr_service.transmitir_nfe(payload)
        print(f"Retorno do Envio - Status: {status}")
        print(json.dumps(resposta, indent=2))
        
        # 3. Salvar no banco
        nota = Nota(
            empresa_id=empresa.id,
            modelo="55",
            status=status,
            valor_total=800.00,
            json_venda=json.dumps(venda_data),
            payload_enviado=json.dumps(payload),
            resposta_integradora=json.dumps(resposta)
        )
        session.add(nota)
        session.commit()
        session.refresh(nota)
        print(f"\nNota salva no banco de dados com ID: {nota.id} e Status: {nota.status}")
        
        # 4. Simular polling/consulta de status
        print("\nSimulando consulta de status (Polling)...")
        ref = resposta.get("referencia") or payload.get("referencia")
        new_status, new_resp = await acbr_service.consultar_status_nfe(ref)
        print(f"Retorno da Consulta - Status: {new_status}")
        print(json.dumps(new_resp, indent=2))
        
        # Atualiza banco
        nota.status = new_status
        nota.resposta_integradora = json.dumps(new_resp)
        if new_status == "autorizada":
            nota.chave_acesso = new_resp.get("chave") or ref
            nota.numero = new_resp.get("numero") or 1001
            nota.serie = new_resp.get("serie") or 1
            
        session.add(nota)
        session.commit()
        session.refresh(nota)
        print(f"Nota atualizada com sucesso no banco - ID: {nota.id}, Status Final: {nota.status}")

if __name__ == "__main__":
    asyncio.run(test_nfe_flow())
