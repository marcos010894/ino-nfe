# 🚀 InnoNFe — Guia Mestre (Comece por aqui)

Este é o arquivo que explica **tudo**: como usar os outros arquivos, qual tecnologia
usar e em que ordem construir. Leia este antes de qualquer outro.

---

## 1. Como funciona desenvolver com IA (leia isso primeiro)

Você **não** vai colar a proposta inteira e pedir "faça o sistema". A IA se perde,
mistura coisas e gera código que não funciona junto. O jeito certo é:

1. **Uma parte por vez.** Cada arquivo numerado (`01`, `02`, `03`...) é uma etapa.
2. **Cola o conteúdo do arquivo** no seu assistente de IA (Claude Code, Cursor, etc.).
3. A IA constrói **só aquela etapa**.
4. **Você testa** seguindo os "Critérios de aceite" no fim de cada arquivo.
5. Deu certo? Passa pro próximo arquivo. Deu erro? Cola o erro pra IA corrigir.

> 💡 **Regra de ouro:** nunca comece a etapa 3 se a 2 não estiver funcionando.
> Cada etapa depende da anterior. Construir na ordem evita 90% dos problemas.

### Como "conversar" com a IA em cada etapa

Um bom pedido pra IA tem 3 partes:
- **Contexto:** "Estou construindo o InnoNFe, um sistema SaaS de emissão fiscal. Já
  terminei a etapa X."
- **A tarefa:** cole a seção "O que vamos construir" do arquivo da etapa.
- **Restrições:** "Use a stack definida no guia (FastAPI + React TS). Não pule etapas.
  Se algo estiver ambíguo, me pergunte antes de codar."

---

## 2. A stack recomendada (as ferramentas)

Escolhi ferramentas que a IA **conhece muito bem** (muito material de treino = menos erros)
e que resolvem sozinhas várias exigências da proposta. Você pode trocar, mas se estiver
começando, siga esta:

Esta arquitetura tem **dois projetos separados**: um backend (o cérebro) e um frontend
(as telas), que conversam por HTTP.

| Necessidade | Ferramenta | Por quê |
|---|---|---|
| Backend / API (o "cérebro") | **FastAPI** (Python) | Rápido, com documentação automática, a IA domina |
| Frontend / telas | **React + TypeScript** (com Vite) | Padrão de mercado pra telas web |
| Banco de dados | **SQLite** (agora) → **MySQL** (depois) | SQLite não precisa instalar nada; troca simples pro MySQL via ORM |
| Modelar as tabelas | **SQLModel + Alembic** | ORM fácil (mesmo autor do FastAPI) + migrations |
| Login/usuários | **JWT no FastAPI** (`python-jose` + `passlib`) | Login seguro construído no próprio backend |
| Guardar certificados A1 (.pfx) | **Upload via FastAPI** + storage (disco/S3) | O backend recebe e guarda o arquivo com segurança |
| Multiempresa (isolar dados) | **Filtro por empresa nas consultas** do backend | O backend garante que cada empresa só vê o que é seu |
| Aparência das telas | **Tailwind CSS + shadcn/ui** | Componentes prontos e bonitos |
| Falar com a SEFAZ | **Integradora fiscal** (Focus NFe, Nuvem Fiscal ou PlugNotas) | Elas cuidam da parte complexa da SEFAZ; você só chama a API delas |

> ⚠️ **Sobre a integradora fiscal:** você **não** vai falar direto com a SEFAZ. Isso é
> extremamente complexo (XML, assinatura digital, esquemas por estado). A proposta já
> prevê isso: você contrata uma integradora, cria uma conta, e o InnoNFe manda os dados
> pra ela. Escolha uma antes da Etapa 05. Veja o arquivo `05-EMISSAO-NFCE.md` para
> critérios de escolha.

### O que você precisa criar/instalar (grátis para começar):
- [ ] **Python 3.11+** e **Node.js** instalados no seu computador
- [ ] Banco: começamos com **SQLite** (nada a instalar — é um arquivo). Depois migramos pro **MySQL**
- [ ] Conta numa **integradora fiscal** (só na Etapa 05, em ambiente de "homologação"/teste)

---

## 3. Ordem de construção (o mapa)

Construa **exatamente nesta ordem**. A coluna "Etapa da proposta" mostra a que parte
da proposta comercial cada arquivo corresponde.

| Arquivo | O que faz | Etapa da proposta |
|---|---|---|
| `01-SETUP.md` | Cria o projeto, conecta ao banco, estrutura de pastas | (base técnica) |
| `02-LOGIN-E-AUTENTICACAO.md` | Tela de login, cadastro de usuários, rotas protegidas | (base técnica) |
| `03-EMPRESAS-E-CERTIFICADOS.md` | Cadastro de empresas + cofre do certificado A1 | Etapa A |
| `04-REGRAS-FISCAIS.md` | Configuração de CFOP, NCM, ICMS, PIS, COFINS por empresa | Etapa B |
| `05-EMISSAO-NFCE.md` | Tela "Emitir Nota" + emissão de NFC-e (síncrona) | Etapa C |
| `06-EMISSAO-NFE.md` | Emissão de NF-e (assíncrona, com controle de status) | Etapa D |
| `07-CENTRAL-DOCUMENTOS.md` | Listagem, filtros, XML/PDF, cancelamento, reprocessar erro | Etapa E |
| `08-EXPORTACOES.md` | Download em lote (ZIP de XML/DANFE) | Etapa F |

> As etapas 01 e 02 não estão na proposta como itens separados, mas **são obrigatórias**:
> sem projeto criado e sem login, nada mais existe. É o alicerce.

---

## 4. O que NÃO faz parte disto (Fase 2)

Pra não perder o foco, estes itens ficam de fora do MVP (a própria proposta define isso):
integração automática InnoSystem↔InnoNFe, NF-e de devolução, inutilização de numeração,
contingência offline, painel white-label, NFS-e (serviços) e dashboards financeiros.

Se a IA sugerir construir qualquer um destes agora, **recuse** — é escopo futuro.

---

## 5. Checklist geral do MVP

- [ ] 01 — Projeto criado e rodando
- [ ] 02 — Login funcionando
- [ ] 03 — Empresas e certificados cadastrados
- [ ] 04 — Regras fiscais configuráveis
- [ ] 05 — NFC-e emitindo em homologação
- [ ] 06 — NF-e emitindo em homologação
- [ ] 07 — Central de documentos completa
- [ ] 08 — Exportação em lote

Quando todos estiverem marcados, o MVP (Fase 1) está pronto. 🎉

---

## 6. Dicas gerais para não sofrer

- **Comece sempre em ambiente de HOMOLOGAÇÃO** (teste) da SEFAZ/integradora. Emitir nota
  fiscal de verdade (produção) tem valor legal — só depois de tudo testado.
- **Faça commits no Git** ao fim de cada etapa que funcionar. Assim você nunca perde
  progresso e pode voltar se a IA quebrar algo.
- **Não guarde senhas nem chaves de API no código.** Elas vão nos arquivos `.env` (backend/frontend)
  (o `01-SETUP.md` explica).
- **Se travar numa etapa, cole o erro completo pra IA.** Mensagem de erro é ouro.
- **Teste cada etapa antes de avançar.** É mais lento parecer, mas é muito mais rápido
  no total.
