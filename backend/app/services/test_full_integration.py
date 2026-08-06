import asyncio
import json
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app.models.database import engine
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.services.seed_company import seed
from app.services.acbr_api import ACBrAPIService

def test_full_flow():
    print("==================================================")
    print("🚀 INICIANDO TESTE END-TO-END NO INNOFISCAL + ACBr")
    print("==================================================")

    # 1. Executar seed de empresa/usuario
    print("\n1. Verificando/Criando Empresa e Usuário de Teste (Seed)...")
    seed()

    client = TestClient(app)

    with Session(engine) as session:
        user = session.exec(select(Usuario)).first()
        empresa = session.exec(select(Empresa)).first()
        
    print(f"✅ Usuário: {user.email}")
    print(f"✅ Empresa: {empresa.razao_social} (CNPJ: {empresa.cnpj})")

    # 2. Obter Token JWT de Autenticação
    print("\n2. Autenticando Usuário no Sistema...")
    login_resp = client.post("/auth/login", json={"email": user.email, "senha": "123456"})
    if login_resp.status_code != 200:
        print(f"❌ Erro ao autenticar: {login_resp.text}")
        return
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Token JWT gerado com sucesso!")


    # 3. Testar Sincronização com ACBr API
    print(f"\n3. Testando Sincronização da Empresa #{empresa.id} com ACBr API...")
    sync_resp = client.post(f"/empresas/{empresa.id}/sincronizar-acbr", headers=headers)
    print(f"Status HTTP: {sync_resp.status_code}")
    print("Resposta ACBr Sync:")
    print(json.dumps(sync_resp.json(), indent=2))
    assert sync_resp.status_code == 200
    assert sync_resp.json()["acbr_sincronizado"] == True
    print("✅ Empresa ligada diretamente e sincronizada no ACBr com sucesso!")

    # 4. Testar Emissão de NFC-e (Modelo 65 - Venda Consumidor)
    print(f"\n4. Testando Emissão de NFC-e (Modelo 65) vinculada à Empresa #{empresa.id}...")
    venda_nfce = {
        "itens": [
            {
                "codigo": "JOIA_001",
                "nome": "ANEL DE PRATA 925 COM ZIRCÔNIA",
                "quantidade": 1,
                "valor_unitario": 150.00
            }
        ],
        "desconto": 10.00,
        "pagamentos": [
            {
                "meio_pagamento": "17", # PIX
                "valor": 140.00
            }
        ],
        "cliente": {
            "nome": "MARCOS PAULO MACHADO AZEVEDO",
            "cpf": "12345678901"
        }
    }

    emit_resp = client.post(
        f"/empresas/{empresa.id}/notas",
        headers=headers,
        json={
            "modelo": "65",
            "json_venda": json.dumps(venda_nfce)
        }
    )
    print(f"Status HTTP Emissão NFC-e: {emit_resp.status_code}")
    res_data = emit_resp.json()
    print("Resposta Emissão NFC-e:")
    print(json.dumps(res_data, indent=2))
    assert emit_resp.status_code == 200
    assert res_data["status"] in ["autorizada", "processando"]
    print("✅ NFC-e Transmitida e Processada pelo ACBr!")

    # 5. Testar Emissão de NF-e (Modelo 55 - Emissão Comercial)
    print(f"\n5. Testando Emissão de NF-e (Modelo 55) vinculada à Empresa #{empresa.id}...")
    venda_nfe = {
        "itens": [
            {
                "codigo": "JOIA_002",
                "nome": "CORRENTE MACHO BRUTO PRATA 925",
                "quantidade": 2,
                "valor_unitario": 300.00
            }
        ],
        "desconto": 0.00,
        "pagamentos": [
            {
                "meio_pagamento": "01", # Dinheiro
                "valor": 600.00
            }
        ]
    }

    emit_nfe_resp = client.post(
        f"/empresas/{empresa.id}/notas",
        headers=headers,
        json={
            "modelo": "55",
            "json_venda": json.dumps(venda_nfe)
        }
    )
    print(f"Status HTTP Emissão NF-e: {emit_nfe_resp.status_code}")
    res_nfe_data = emit_nfe_resp.json()
    print("Resposta Emissão NF-e:")
    print(json.dumps(res_nfe_data, indent=2))
    assert emit_nfe_resp.status_code == 200
    print("✅ NF-e Modelo 55 Transmitida com Sucesso!")

    print("\n==================================================")
    print("🎉 TODOS OS TESTES END-TO-END PASSARAM COM SUCESSO!")
    print("==================================================")

if __name__ == "__main__":
    test_full_flow()
