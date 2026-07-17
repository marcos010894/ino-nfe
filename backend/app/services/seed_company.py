from sqlmodel import Session, select
from app.models.database import engine
from app.models.usuario import Usuario
from app.models.empresa import Empresa
from app.models.regra_fiscal import RegraFiscal
from datetime import datetime

def seed():
    with Session(engine) as session:
        # 1. Encontrar ou criar um usuário padrão
        user = session.exec(select(Usuario)).first()
        if not user:
            print("Nenhum usuário cadastrado. Criando usuário admin...")
            from app.api.auth import get_password_hash
            user = Usuario(
                email="christian.silva@netminas.com.br",
                senha_hash=get_password_hash("DQMCyE5s8D@5sVY"),
                nome="Christian Silva",
                criado_em=datetime.utcnow()
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            print(f"Usuário criado: {user.email}")
        
        # 2. Encontrar ou criar a empresa
        cnpj_limpo = "15278447000102"
        empresa = session.exec(select(Empresa).where(Empresa.cnpj == cnpj_limpo)).first()
        if not empresa:
            print(f"Criando empresa {cnpj_limpo}...")
            empresa = Empresa(
                usuario_id=user.id,
                razao_social="INNOBYTE LTDA",
                nome_fantasia="PLAYCELL",
                cnpj=cnpj_limpo,
                inscricao_estadual="",
                cep="37200000",
                logradouro="JUSCELINO KUBITSCHECK",
                numero="591",
                bairro="CENTRO",
                cidade="LAVRAS",
                uf="MG",
                contato_telefone="3599999999",
                contato_email="contato@playcell.com.br",
                regime_tributario="Simples Nacional",
                csc_id="",
                csc_token="",
                criado_em=datetime.utcnow()
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)
            print(f"Empresa criada com ID: {empresa.id}")
        else:
            print(f"Empresa {cnpj_limpo} já existe.")

        # 3. Criar ou atualizar a Regra Fiscal Padrão para a empresa
        regra = session.exec(select(RegraFiscal).where(RegraFiscal.empresa_id == empresa.id)).first()
        if not regra:
            print(f"Criando regra fiscal padrão para a empresa {empresa.id}...")
            regra = RegraFiscal(
                empresa_id=empresa.id,
                nome="Venda de Joia / Mercadoria - Dentro do Estado",
                cfop="5102",
                ncm_padrao="71131900",  # Joias/Semijoias
                origem_icms="0",
                cst_csosn="102",  # Simples Nacional sem crédito
                icms_aliquota=0.0,
                pis_cst="07",  # Isento
                pis_aliquota=0.0,
                cofins_cst="07",  # Isento
                cofins_aliquota=0.0,
                padrao=True,
                criado_em=datetime.utcnow()
            )
            session.add(regra)
            session.commit()
            session.refresh(regra)
            print(f"Regra fiscal criada com ID: {regra.id}")
        else:
            print(f"Regra fiscal padrão já existe para a empresa {empresa.id}.")

if __name__ == "__main__":
    seed()
