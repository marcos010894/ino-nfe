# 02 — Login e Autenticação (JWT no FastAPI)

> **Objetivo:** criar o sistema de login. Ao fim desta etapa, só quem tem usuário e
> senha consegue usar o sistema. O login será feito com **JWT** no backend FastAPI —
> nada de serviço externo, o próprio backend cuida disso.

## Pré-requisitos
- [ ] Etapa `01-SETUP.md` concluída (backend FastAPI + frontend React rodando e conectados).
- [ ] Banco SQLite funcionando via SQLModel.

---

## Como funciona login com JWT (rapidinho)

JWT (JSON Web Token) é um "crachá digital". O fluxo é:

```
1. Usuário manda e-mail + senha pro backend (POST /auth/login)
2. Backend confere a senha (comparando com a versão criptografada no banco)
3. Se bater, o backend devolve um TOKEN (o crachá)
4. O React guarda esse token e o envia em toda chamada seguinte (no cabeçalho Authorization)
5. O backend valida o token em cada rota protegida
```

> 🔐 **Regra de segurança:** a senha do usuário **nunca** é guardada em texto puro. Ela é
> transformada por um "hash" (com `passlib`/`bcrypt`) — um caminho só de ida. Nem você
> consegue ver a senha original. Isso é o padrão correto; não invente nada aqui.

---

## O que vamos construir

### No backend (FastAPI)
1. **Tabela `usuarios`** (SQLModel): id, nome, email, senha_hash, ativo, criado_em.
2. **Rota de cadastro** `POST /auth/register` — cria usuário com a senha já "hasheada".
3. **Rota de login** `POST /auth/login` — confere e-mail/senha e devolve o token JWT.
4. **Rota "quem sou eu"** `GET /auth/me` — devolve os dados do usuário logado (testa o token).
5. **Uma "dependência" de proteção** (`get_current_user`) que qualquer rota pode usar para
   exigir login. As rotas das próximas etapas (empresas, notas...) vão usar isso.

### No frontend (React)
1. **Tela de Login** (e-mail + senha).
2. **Tela de Cadastro** de usuário.
3. Guardar o token após o login e enviá-lo automaticamente nas chamadas (interceptor do axios).
4. **Rotas protegidas** no React Router: quem não está logado é mandado pro `/login`.
5. **Logout** (apaga o token e volta pro login).
6. **Um layout de painel** (menu lateral simples) que aparece depois do login.

> 💡 Neste MVP, o "usuário" é você/sua equipe que opera o sistema — **não** é o lojista
> cliente final. Acesso do cliente final é Fase 2 (fora do escopo).

### Estrutura das telas no React
```
src/
├── pages/
│   ├── Login.tsx
│   ├── Cadastro.tsx
│   └── dashboard/
│       └── Home.tsx        # painel inicial (vazio por ora)
├── components/
│   └── Layout.tsx          # menu lateral + verificação de login
└── lib/
    ├── api.ts              # axios com interceptor que injeta o token
    └── auth.ts             # guardar/ler/apagar o token, checar se está logado
```

---

## Como pedir para a IA

**Passo 1 — Backend (login com JWT):**

> "No InnoNFe (FastAPI + SQLModel + SQLite), quero autenticação com **JWT**. Preciso:
> 1. Uma tabela `usuarios` (SQLModel): id, nome, email (único), senha_hash, ativo, criado_em.
>    Gerar a migration com Alembic.
> 2. Hash de senha com `passlib` (bcrypt) — nunca guardar senha em texto puro.
> 3. `POST /auth/register` (cria usuário), `POST /auth/login` (retorna token JWT assinado
>    com `SECRET_KEY` do `.env`, usando `python-jose`) e `GET /auth/me` (dados do logado).
> 4. Uma dependência `get_current_user` que valida o token e protege rotas, para eu
>    reusar nas próximas etapas.
> Comente o código e me explique o fluxo, porque estou aprendendo."

**Passo 2 — Frontend (telas + proteção):**

> "Agora no frontend React + TS. Preciso:
> 1. Tela de **Login** (`/login`) que chama `POST /auth/login` e guarda o token.
> 2. Tela de **Cadastro** (`/cadastro`) que chama `POST /auth/register`.
> 3. Em `src/lib/api.ts`, um **interceptor do axios** que adiciona o token no cabeçalho
>    `Authorization: Bearer <token>` de toda requisição.
> 4. **Rotas protegidas** com react-router: se não houver token válido, redireciona pra
>    `/login`.
> 5. Um **layout de painel** (`Layout.tsx`) com menu lateral (itens: Dashboard, Empresas,
>    Emitir Nota, Documentos) e botão de **Logout** (apaga o token e volta pro login).
> 6. Use shadcn/ui nos campos e botões. Comente o código."

---

## Critérios de aceite
- [ ] Consigo criar um usuário pela tela de cadastro (aparece na tabela `usuarios`).
- [ ] A senha no banco está em **hash**, não em texto puro.
- [ ] Consigo fazer login e recebo um token.
- [ ] Depois de logar, vejo o painel com o menu lateral.
- [ ] `GET /auth/me` (dá pra testar em `/docs`) retorna meus dados quando envio o token.
- [ ] Se eu tentar abrir uma tela interna sem token (aba anônima), sou mandado pro `/login`.
- [ ] O Logout funciona e me devolve pro login.

---

## Dicas e armadilhas comuns
- **Onde guardar o token no React:** o mais simples é `localStorage`. Funciona bem pro MVP.
  (Existe debate sobre segurança de token em localStorage — anote como ajuste futuro, mas
  não trave o MVP com isso agora.)
- **Erro 401 em tudo:** normalmente é o interceptor do axios não enviando o token, ou o
  token expirado. Confira o cabeçalho `Authorization`.
- **Como criar o primeiro usuário:** como é uso interno, você pode chamar o `/auth/register`
  direto pela documentação `/docs` do FastAPI, sem precisar de tela pública de cadastro.
  Considere até proteger/remover o cadastro público depois — anote como ajuste futuro.
- Defina um **tempo de expiração** pro token (ex: algumas horas). Peça isso à IA.
- Commit no Git ao terminar. ✅
