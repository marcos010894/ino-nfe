# 01 — Setup e Fundação (FastAPI + React TS)

> **Objetivo:** criar o projeto do zero. Diferente de um projeto "tudo num lugar só",
> aqui teremos **dois projetos separados** que conversam entre si:
> - **Backend** (o "cérebro"): FastAPI, em Python. Cuida do banco, das regras e da emissão.
> - **Frontend** (as "telas"): React + TypeScript. É o que o operador vê e clica.
>
> Ao fim desta etapa você tem os dois rodando na sua máquina e conversando entre si.

## Pré-requisitos
- [ ] **Python** instalado (3.11+) — [python.org](https://python.org)
- [ ] **Node.js** instalado (LTS) — [nodejs.org](https://nodejs.org) — necessário pro React
- [ ] O banco: começamos com **SQLite** (não precisa instalar nada — é só um arquivo no
      projeto). Depois migramos para **MySQL** sem reescrever o código (ver "Estratégia de
      banco" abaixo).
- [ ] Um editor de código (VS Code é o mais comum)

---

## Como as duas partes conversam

```
[ React (navegador) ]  --- chamadas HTTP (axios/fetch) --->  [ FastAPI (servidor) ]
     telas, botões                                              regras, banco, integradora
                                                                        |
                                                                        v
                                                             [ SQLite → depois MySQL ]
```

O React **nunca** fala com o banco nem com a integradora fiscal diretamente. Ele só pede
coisas pro FastAPI ("me lista as empresas", "emite essa nota"), e o FastAPI faz o trabalho
pesado. Isso é importante pra segurança: certificado, senhas e chaves ficam **só no backend**.

---

## Estratégia de banco: SQLite agora, MySQL depois

Vamos **começar com SQLite** (banco num único arquivo, zero instalação — perfeito pra
desenvolver) e **migrar pro MySQL** mais tarde, quando o sistema for pra valer.

Isso funciona bem porque usamos o **SQLModel** (um ORM). Você escreve o código uma vez, e
ele fala com qualquer banco. Na prática, migrar significa basicamente **trocar a
`DATABASE_URL`** e instalar o driver do MySQL:

```
# Agora (desenvolvimento):
DATABASE_URL=sqlite:///./innonfe.db

# Depois (produção, MySQL):
DATABASE_URL=mysql+pymysql://usuario:senha@host:3306/innonfe
```

> ⚠️ **Para a migração ser tranquila, siga estas regras desde o começo:**
> - **Nunca escreva SQL "cru" específico de um banco.** Sempre acesse os dados pelo
>   SQLModel. Assim o código não fica preso ao SQLite.
> - **Use o Alembic com modo `batch`** (`render_as_batch=True`). O SQLite tem limitações
>   pra alterar tabelas, e o modo batch resolve isso. Peça pra IA já configurar assim.
> - **Use tipos de dados padrão** (texto, número, data, booleano). Evite recursos
>   exclusivos de um banco.
> - Quando trocar pro MySQL, rode as migrations do Alembic no banco novo e os dados de
>   teste do SQLite ficam pra trás (o `.db` é só de desenvolvimento mesmo).

---

## O que vamos construir

1. **Projeto backend (FastAPI)** rodando em `http://localhost:8000`.
2. **Projeto frontend (React + TS com Vite)** rodando em `http://localhost:5173`.
3. **Conexão do backend com o banco (SQLite).**
4. **CORS configurado** no backend (senão o navegador bloqueia as chamadas do React).
5. **Um "hello world" de ponta a ponta:** o React chama uma rota do FastAPI e mostra a
   resposta na tela — provando que tudo está conectado.

### Estrutura de pastas sugerida
```
innonfe/
├── backend/                 # FastAPI (Python)
│   ├── app/
│   │   ├── main.py          # ponto de entrada da API + CORS
│   │   ├── core/            # config, variáveis de ambiente, segurança (JWT)
│   │   ├── models/          # tabelas do banco (SQLModel / SQLAlchemy)
│   │   ├── schemas/         # validação de entrada/saída (Pydantic)
│   │   ├── api/             # os endpoints (rotas)
│   │   └── services/        # regras de negócio (emissão, integradora fiscal)
│   ├── alembic/             # controle de versão do banco (migrations)
│   ├── .env                 # chaves secretas — NUNCA vai pro Git
│   └── requirements.txt
└── frontend/                # React + TypeScript (Vite)
    ├── src/
    │   ├── pages/           # telas (login, empresas, emitir nota...)
    │   ├── components/      # componentes reutilizáveis
    │   ├── lib/             # cliente da API (axios), controle de login
    │   └── App.tsx          # rotas do frontend (react-router)
    ├── .env                 # VITE_API_URL etc.
    └── package.json
```

### Ferramentas de cada lado (o que instalar)

**Backend (Python):**
- `fastapi` + `uvicorn` — o framework e o servidor
- `sqlmodel` — para modelar as tabelas (feito pelo mesmo autor do FastAPI, fácil pra começar)
- `alembic` — migrations (versionar mudanças no banco)
- `pymysql` — driver do MySQL (só será usado quando migrar; o SQLite já vem no Python)
- `pydantic-settings` — ler variáveis de ambiente
- `python-jose[cryptography]` + `passlib[bcrypt]` — login com JWT (etapa 02)
- `python-multipart` — upload de arquivos, ex: certificado (etapa 03)
- `cryptography` — criptografar a senha do certificado (etapa 03)
- `httpx` — chamar a API da integradora fiscal (etapa 05)

**Frontend (React):**
- Projeto criado com **Vite** (`react-ts`)
- `axios` — fazer as chamadas HTTP pro backend
- `react-router-dom` — navegação entre telas
- `tailwindcss` + `shadcn/ui` — aparência (funciona com Vite também)
- (opcional) `@tanstack/react-query` — facilita buscar/atualizar dados da API

### Variáveis de ambiente

**backend/.env**
```
DATABASE_URL=sqlite:///./innonfe.db          # depois: mysql+pymysql://usuario:senha@host:3306/innonfe
SECRET_KEY=uma-chave-longa-e-aleatoria       # assina os tokens de login (JWT)
CERT_ENCRYPTION_KEY=outra-chave-aleatoria     # criptografa a senha do certificado
```

**frontend/.env**
```
VITE_API_URL=http://localhost:8000
```

> ⚠️ Crie um `.gitignore` em cada projeto incluindo, no backend, `.env`, `venv/` e o
> arquivo do banco `*.db` (o SQLite é só de desenvolvimento, não vai pro Git); e no
> frontend, `.env` e `node_modules`. Essas chaves e dados **nunca** podem ir pro GitHub.

---

## Como pedir para a IA

**Passo 1 — Backend:**

> "Estou começando o InnoNFe, um SaaS de emissão fiscal. O backend será em **FastAPI
> (Python)**. Quero:
> 1. Criar a estrutura de pastas do backend que descrevo abaixo.
> 2. Configurar o FastAPI com `uvicorn`, com **CORS** liberado para `http://localhost:5173`.
> 3. Configurar conexão com o banco usando **SQLModel**, lendo `DATABASE_URL` do `.env`.
>    Começar com **SQLite** (`sqlite:///./innonfe.db`), mas escrever de forma **portável**
>    para depois trocar pra MySQL só mudando a `DATABASE_URL`.
> 4. Configurar **Alembic** para migrations, com `render_as_batch=True` (necessário pro
>    SQLite conseguir alterar tabelas).
> 5. Criar um endpoint de teste `GET /health` que retorna `{"status": "ok"}`.
> 6. Um `requirements.txt` com as dependências: [cole a lista de pacotes do backend].
> 7. O `.gitignore` com `.env`, `venv/` e `*.db`.
> Me dê os comandos passo a passo (criar ambiente virtual, instalar, rodar) e comente o
> código, porque estou aprendendo. [cole a estrutura de pastas]"

**Passo 2 — Frontend:**

> "Agora o frontend do InnoNFe em **React + TypeScript com Vite**. Quero:
> 1. Criar o projeto com Vite (template react-ts) e instalar: axios, react-router-dom,
>    tailwindcss, shadcn/ui.
> 2. Configurar o Tailwind e o shadcn/ui.
> 3. Criar um cliente axios em `src/lib/api.ts` que usa `VITE_API_URL` do `.env`.
> 4. Uma página inicial que chama `GET /health` do backend e mostra o resultado na tela.
> 5. O `.gitignore` com `.env` e `node_modules`.
> Comente o código."

---

## Critérios de aceite (como saber que funcionou)
- [ ] Rodando o backend, `http://localhost:8000/health` retorna `{"status": "ok"}`.
- [ ] `http://localhost:8000/docs` abre a documentação automática do FastAPI (Swagger).
- [ ] Rodando o frontend, `http://localhost:5173` abre a página inicial.
- [ ] A página inicial do React **mostra a resposta** do `/health` — prova que os dois
      estão conectados (isso testa o CORS também).
- [ ] O backend cria o arquivo `innonfe.db` (SQLite) e conecta sem erros.
- [ ] Fiz `git init` e o primeiro commit.

---

## Dicas e armadilhas comuns
- **Erro de CORS** é o problema nº 1 nessa arquitetura. Se o React não consegue chamar a
  API ("blocked by CORS policy"), é porque o FastAPI não liberou a origem do frontend.
  O código do CORS (`CORSMiddleware`) precisa incluir `http://localhost:5173`.
- Use um **ambiente virtual** no Python (`venv`) para o backend não bagunçar seu sistema.
  Peça pra IA te mostrar como ativar (`source venv/bin/activate` no Linux/Mac,
  `venv\Scripts\activate` no Windows).
- A documentação automática em `/docs` é seu melhor amigo: dá pra testar as rotas do
  backend por ali, sem precisar do frontend.
- Rode **backend e frontend em dois terminais separados**, ao mesmo tempo.
- Faça um commit no Git agora. É o seu "ponto de restauração". ✅
