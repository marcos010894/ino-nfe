# Consulta de Notas + SSO — InnoSystem → InnoFiscal

**Ambiente:** `https://inno-fiscal.fly.dev`
**Token:** o mesmo `X-API-Key` da integração `/receber-venda`. InnoFiscal → **Notas Recebidas** → canto superior direito.

Três coisas cobertas:

- **Listar notas do cliente** — status, chave, valor, motivo de rejeição.
- **Detalhar uma nota** — payload original + resposta bruta da SEFAZ.
- **SSO** — abrir a tela de emissão do InnoFiscal sem o cliente fazer login.

---

## 1. Listar notas

```
GET https://inno-fiscal.fly.dev/integracao/notas
```

**Headers:**

| Header      | Valor                          |
|-------------|--------------------------------|
| `X-API-Key` | Token do usuário do InnoFiscal |

**Query params (todos opcionais):**

| Param        | Valores                                                       |
|--------------|---------------------------------------------------------------|
| `status`     | `rascunho`, `processando`, `autorizada`, `rejeitada`, `cancelada` |
| `modelo`     | `55` (NF-e) ou `65` (NFC-e)                                   |
| `empresa_id` | int — empresa emissora dentro do InnoFiscal                   |
| `limit`      | 1–200 (default 50)                                            |
| `offset`     | int (default 0)                                               |

**curl:**

```bash
curl -H "X-API-Key: lqy6JDX_6NepAtqXanleJo0uSbpaGLBscRji88rf10s" \
  "https://inno-fiscal.fly.dev/integracao/notas?status=autorizada&modelo=65&limit=20"
```

**Resposta (200 OK):**

```json
[
  {
    "id": 128,
    "modelo": "65",
    "status": "autorizada",
    "chave_acesso": "31260815278447000102650010000000451234567890",
    "numero": 45,
    "serie": 1,
    "valor_total": 1032.85,
    "empresa_id": 3,
    "xml_url": "/empresas/3/notas/128/xml",
    "pdf_url": "/empresas/3/notas/128/pdf",
    "criado_em": "2026-08-12T14:22:18.123Z",
    "atualizado_em": "2026-08-12T14:22:20.981Z",
    "motivo_rejeicao": null,
    "codigo_status": "100"
  },
  {
    "id": 127,
    "modelo": "65",
    "status": "rejeitada",
    "chave_acesso": null,
    "numero": null,
    "serie": null,
    "valor_total": 1032.85,
    "empresa_id": 3,
    "xml_url": null,
    "pdf_url": null,
    "criado_em": "2026-08-12T14:20:10.001Z",
    "atualizado_em": "2026-08-12T14:20:11.442Z",
    "motivo_rejeicao": "Rejeicao: Total do Valor Aproximado dos Tributos difere do somatorio dos itens",
    "codigo_status": "685"
  }
]
```

**Campos:**

| Campo             | Tipo    | Nota                                                        |
|-------------------|---------|-------------------------------------------------------------|
| `id`              | int     | id da nota no InnoFiscal                                    |
| `status`          | string  | `rascunho`, `processando`, `autorizada`, `rejeitada`, `cancelada` |
| `chave_acesso`    | string  | 44 dígitos — só quando `autorizada`                         |
| `numero`, `serie` | int     | Preenchidos só quando enviado à SEFAZ                       |
| `xml_url` / `pdf_url` | string | Caminho relativo — baixar via UI ou via `/empresas/{id}/notas/{nota_id}/xml` autenticado |
| `motivo_rejeicao` | string  | Motivo da SEFAZ quando `rejeitada` (extraído da resposta ACBr) |
| `codigo_status`   | string  | cStat SEFAZ (ex: `100` = autorizado, `685` = tributos divergentes) |

---

## 2. Detalhar uma nota

```
GET https://inno-fiscal.fly.dev/integracao/notas/{id}
```

**curl:**

```bash
curl -H "X-API-Key: lqy6JDX_6NepAtqXanleJo0uSbpaGLBscRji88rf10s" \
  "https://inno-fiscal.fly.dev/integracao/notas/128"
```

Devolve tudo do endpoint de listagem **mais**:

| Campo                  | Tipo    | Nota                                             |
|------------------------|---------|--------------------------------------------------|
| `json_venda`           | object  | O payload original que o InnoSystem enviou       |
| `resposta_integradora` | object  | Retorno bruto da ACBr (autorizacao, cancelamento, error…) |

---

## 3. SSO — abrir a tela de emissão sem login

Fluxo pro cliente clicar num botão no InnoSystem e cair já autenticado na tela de emissão do InnoFiscal — sem digitar email/senha.

### Passo 1: pegar um JWT curto

**No servidor do InnoSystem** (não no browser), trocar o token de integração por um JWT de 15 minutos:

```
POST https://inno-fiscal.fly.dev/integracao/sessao?rascunho_id={id}
```

`rascunho_id` é opcional — se informado, o usuário cai direto naquele rascunho. Sem ele, cai na tela de emissão em branco.

**curl:**

```bash
curl -X POST -H "X-API-Key: lqy6JDX_6NepAtqXanleJo0uSbpaGLBscRji88rf10s" \
  "https://inno-fiscal.fly.dev/integracao/sessao?rascunho_id=42"
```

**Resposta (200 OK):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "usuario_id": 7,
  "redirect_url": "/sso?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...&rascunho=42"
}
```

### Passo 2: redirecionar o usuário

Montar a URL final e redirecionar (ou abrir em nova aba):

```
https://inno-fiscal.fly.dev/sso?token={access_token}&rascunho={id}
```

Ou usar direto o `redirect_url` que veio na resposta:

```
https://inno-fiscal.fly.dev{redirect_url}
```

A rota `/sso` no InnoFiscal:

1. Lê o `token` da URL, grava como sessão do usuário.
2. Remove o token da URL (não fica em histórico do browser).
3. Redireciona pra `/emitir?rascunho={id}` — tela de emissão já com o rascunho carregado.

### Exemplo integrado (Node.js no backend do InnoSystem)

```js
// InnoSystem gera link de "Emitir no InnoFiscal" para um pedido
async function gerarLinkEmissao(clienteApiKey, rascunhoId) {
  const url = `https://inno-fiscal.fly.dev/integracao/sessao?rascunho_id=${rascunhoId}`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "X-API-Key": clienteApiKey },
  });
  if (!resp.ok) throw new Error(`SSO falhou: ${resp.status}`);
  const data = await resp.json();
  return `https://inno-fiscal.fly.dev${data.redirect_url}`;
}
```

### Regras de segurança

- O `X-API-Key` **nunca** vai pro browser. Só o InnoSystem (server-side) conhece.
- O JWT retornado vale **15 minutos**. Não guardar em cache — pedir na hora que o usuário clicar.
- `rascunho_id` é validado: se não pertencer ao dono do token, retorna 404.
- URL do `/sso` é reescrita pelo React com `replace` — o JWT some do histórico do browser assim que a tela carrega.

---

## Erros

| HTTP | Endpoint(s)                    | detail                                             |
|------|--------------------------------|----------------------------------------------------|
| 401  | todos                          | `Header X-API-Key é obrigatório para integração.`  |
| 401  | todos                          | `X-API-Key inválida ou usuário não encontrado.`    |
| 403  | todos                          | `Usuário inativo.`                                 |
| 404  | `/integracao/notas/{id}`       | `Nota não encontrada.`                             |
| 404  | `/integracao/sessao`           | `Rascunho não pertence ao usuário do token.`       |
