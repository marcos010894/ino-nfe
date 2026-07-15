# 03 — Empresas e Cofre de Certificados (Etapa A)

> **Objetivo:** cadastrar as empresas (lojas clientes) e guardar com segurança o
> certificado digital A1 de cada uma. Isto é o coração do "multiempresa".

## Pré-requisitos
- [ ] Etapas `01` e `02` concluídas.
- [ ] Login funcionando.

---

## O que vamos construir

### 3.1. Cadastro de Empresas
Um CRUD (criar, listar, editar, excluir) de empresas com os campos:
- Razão Social, Nome Fantasia
- CNPJ, Inscrição Estadual (IE)
- Endereço completo (CEP, logradouro, número, bairro, cidade, UF)
- Contato (telefone, e-mail)
- Regime tributário (ex: Simples Nacional, Lucro Presumido) — importante pras regras fiscais

### 3.2. Cofre de Certificados
- Upload do arquivo do certificado **A1** (`.pfx` ou `.p12`).
- Guardar a **senha** do certificado de forma **criptografada** (nunca em texto puro).
- Mostrar a data de validade do certificado (e avisar quando estiver perto de vencer).

### 3.3. Credenciais NFC-e
- Campo para o **Token CSC** (Código de Segurança do Contribuinte) e o **ID do CSC**,
  emitidos pela SEFAZ de cada estado. São necessários pra emitir NFC-e (modelo 65).

---

## Modelo de dados (tabelas no banco)

```
empresas
├── id
├── razao_social
├── nome_fantasia
├── cnpj
├── inscricao_estadual
├── endereco_* (cep, logradouro, numero, bairro, cidade, uf)
├── contato_telefone, contato_email
├── regime_tributario
├── csc_id            # ID do CSC (NFC-e)
├── csc_token         # Token do CSC (criptografado)
├── criado_em

certificados
├── id
├── empresa_id        # liga ao registro em "empresas"
├── arquivo_path      # caminho do .pfx (pasta protegida no servidor ou storage S3)
├── senha_criptografada
├── validade          # data de vencimento
├── criado_em
```

---

## ⚠️ Segurança (leia com atenção — isso é sério)

O certificado A1 e sua senha são **extremamente sensíveis**: com eles, alguém pode
emitir notas fiscais no nome da empresa. Portanto:

- **O arquivo `.pfx`** é enviado ao backend (FastAPI) e guardado num local **privado**:
  uma pasta fora do acesso público do servidor (ex: `backend/storage/certificados/`) ou
  um bucket S3 privado. Nunca numa pasta pública/servida diretamente.
- **A senha do certificado** deve ser **criptografada** antes de salvar no banco, usando a
  biblioteca `cryptography` (Python) com a chave `CERT_ENCRYPTION_KEY` do `.env`. Nunca
  salve a senha em texto puro.
- **Toda a criptografia/descriptografia acontece no backend**, nunca no navegador.
- **Isolamento multiempresa:** como não usamos RLS de banco, é o **backend** que garante o
  isolamento — toda consulta filtra pela empresa/usuário logado. Nunca deixe uma rota
  devolver dados de uma empresa sem checar a quem pertence.

> Se você não entende algo de segurança aqui, peça pra IA **explicar** antes de aceitar
> o código. Não pule esta parte.

---

## Como pedir para a IA

> "No InnoNFe, quero construir o módulo de Empresas e o Cofre de Certificados (é um
> sistema multiempresa). Preciso:
> 1. Criar as tabelas `empresas` e `certificados` com **SQLModel** e gerar a migration
>    com Alembic. [cole os campos das tabelas acima]
> 2. Um CRUD completo de empresas (rotas FastAPI protegidas por login + telas React) com
>    os campos: [cole a lista de campos acima].
> 3. Upload do certificado A1 (.pfx/.p12) via FastAPI (`python-multipart`), salvando o
>    arquivo numa **pasta privada** do servidor (ou bucket S3 privado).
> 4. Guardar a senha do certificado **criptografada** com a biblioteca `cryptography`
>    (Python), usando `CERT_ENCRYPTION_KEY` do `.env`, tudo **no backend**.
> 5. Ler a data de validade do certificado e exibir na listagem, com um aviso visual
>    quando faltar menos de 30 dias.
> 6. Campos para CSC ID e CSC Token (NFC-e) no cadastro da empresa, com o token guardado
>    de forma segura.
> Comente o código e me explique a parte de segurança. Use shadcn/ui nas telas."

---

## Critérios de aceite
- [ ] Consigo cadastrar uma empresa nova com todos os campos.
- [ ] Consigo listar, editar e excluir empresas.
- [ ] Consigo fazer upload de um certificado `.pfx` e ele fica salvo num local privado (não acessível publicamente).
- [ ] A senha do certificado não aparece em texto puro no banco (está criptografada).
- [ ] A validade do certificado aparece na tela.
- [ ] Os campos CSC ID e CSC Token existem e salvam.

---

## Dicas e armadilhas comuns
- Para testar, use um **certificado A1 de teste** ou o certificado real de uma empresa
  sua — mas em ambiente de desenvolvimento.
- Ler a validade do `.pfx` em Python: use a biblioteca `cryptography` (`load_key_and_certificates`). Peça pra IA cuidar disso.
- Erro comum: salvar o `.pfx` numa pasta servida publicamente pelo servidor. Confirme que o local é privado (fora de `static`/rotas públicas).
- Commit no Git ao terminar. ✅
