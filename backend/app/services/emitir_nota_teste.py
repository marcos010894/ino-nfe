import asyncio
import json
from datetime import datetime
from sqlmodel import Session, select
from app.models.database import engine, init_db
from app.models.usuario import Usuario
from app.models.empresa import Empresa
from app.models.regra_fiscal import RegraFiscal
from app.models.nota import Nota
from app.services.acbr_api import ACBrAPIService
from app.services.seed_company import seed

def rodar_emissao_demonstrativa():
    print("=" * 65)
    print("      🧾 INNOFISCAL - EMISSÃO DE NOTA FISCAL EM HOMOLOGAÇÃO")
    print("=" * 65)

    # 1. Garantir Banco e Seed de Empresa
    init_db()
    seed()

    with Session(engine) as session:
        empresa = session.exec(select(Empresa)).first()
        regra = session.exec(select(RegraFiscal).where(RegraFiscal.empresa_id == empresa.id)).first()

        if not empresa or not regra:
            print("❌ Empresa ou Regra Fiscal não encontradas.")
            return

        print(f"\n🏢 EMISSOR: {empresa.razao_social}")
        print(f"   CNPJ: {empresa.cnpj}")
        print(f"   UF/Cidade: {empresa.uf} - {empresa.cidade}")
        print(f"   Regime: {empresa.regime_tributario}")
        print(f"   Status ACBr: {'✅ Conectado / Homologado' if empresa.acbr_sincronizado else '⚠️ Homologação Ativa'}")

        print(f"\n📋 REGRA FISCAL APLICADA: {regra.nome}")
        print(f"   CFOP: {regra.cfop} | NCM: {regra.ncm_padrao} | CSOSN: {regra.cst_csosn}")

        # 2. Dados da Venda de Teste (Exemplo de Joia/Semijoia no PDV)
        venda_data = {
            "itens": [
                {
                    "codigo": "JOIA-7788",
                    "nome": "ANEL EM PRATA 925 COM CRISTAL DE QUARTZO",
                    "quantidade": 1.0,
                    "valor_unitario": 280.00
                },
                {
                    "codigo": "JOIA-1102",
                    "nome": "FLANELA MÁGICA PARA POLIMENTO",
                    "quantidade": 2.0,
                    "valor_unitario": 15.00
                }
            ],
            "desconto": 20.00,
            "pagamentos": [
                {
                    "meio_pagamento": "17", # Pix
                    "valor": 290.00
                }
            ],
            "cliente": {
                "nome": "CLIENTE TESTE DEMONSTRATIVO",
                "cpf": "111.444.777-35"
            }
        }

        print("\n🛒 ITENS DA VENDA:")
        subtotal = 0
        for idx, item in enumerate(venda_data["itens"], 1):
            total_item = item["quantidade"] * item["valor_unitario"]
            subtotal += total_item
            print(f"   {idx}. [{item['codigo']}] {item['nome']}")
            print(f"      Qtd: {item['quantidade']} x R$ {item['valor_unitario']:.2f} = R$ {total_item:.2f}")

        desconto = venda_data["desconto"]
        total_final = subtotal - desconto

        print(f"\n   Subtotal: R$ {subtotal:.2f}")
        print(f"   Desconto: R$ {desconto:.2f}")
        print(f"   TOTAL FINAL: R$ {total_final:.2f} (Pagamento: PIX)")

        # 3. Montar Payload e Transmitir Nota
        print("\n⚡ Montando pacote XML/JSON e transmitindo para a SEFAZ (Homologação)...")
        acbr_service = ACBrAPIService()
        payload = acbr_service.montar_payload_nfce(empresa, regra, venda_data, modelo=65)

        # Transmissão síncrona
        status, resposta = asyncio.run(acbr_service.transmitir_nfce(payload))

        # 4. Salvar Nota emitida no banco de dados local
        nova_nota = Nota(
            empresa_id=empresa.id,
            usuario_id=empresa.usuario_id,
            modelo="65",
            status=status,
            valor_total=total_final,
            json_venda=json.dumps(venda_data),
            payload_enviado=json.dumps(payload),
            resposta_integradora=json.dumps(resposta),
            chave_acesso=resposta.get("chave"),
            numero=resposta.get("numero"),
            serie=resposta.get("serie"),
            criado_em=datetime.utcnow()
        )
        session.add(nova_nota)
        session.commit()
        session.refresh(nova_nota)

        # 5. Exibir Resultado da Nota Fiscais
        print("\n" + "=" * 65)
        print("🎉 NOTA FISCAL EMITIDA COM SUCESSO NO INNOFISCAL!")
        print("=" * 65)
        print(f"🆔 ID da Nota no Banco: #{nova_nota.id}")
        print(f"📌 Modelo: {nova_nota.modelo} (NFC-e Consumidor Eletrônica)")
        print(f"🟢 Status: {nova_nota.status.upper()}")
        print(f"🔑 Chave de Acesso (SEFAZ 44 Dígitos):\n   {nova_nota.chave_acesso}")
        print(f"🔢 Número da Nota: {nova_nota.numero} | Série: {nova_nota.serie}")
        print(f"📄 Link DANFE (Impressão Bobina): http://localhost:8000/empresas/{empresa.id}/notas/{nova_nota.id}/pdf")
        print(f"📁 Link XML da Nota: http://localhost:8000/empresas/{empresa.id}/notas/{nova_nota.id}/xml")
        print("=" * 65)

if __name__ == "__main__":
    rodar_emissao_demonstrativa()
