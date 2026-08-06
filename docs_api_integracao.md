# Guia de Integração API - InnoFiscal (Receber Vendas)

A plataforma InnoFiscal permite que o seu sistema externo (ou qualquer outra plataforma) injete automaticamente as informações de uma nova venda. Quando essa injeção ocorre, o InnoFiscal cria um **rascunho de Nota Fiscal** vinculado à sua conta, o qual poderá ser editado e emitido na interface web depois.

---

## 1. Como obter a chave da API (X-API-Key)

Para enviar os dados, o seu sistema externo precisa se identificar.
Ao fazer **login** no painel web pela primeira vez, o sistema irá gerar automaticamente uma chave de integração exclusiva para a sua conta.
- Faça o login com o seu usuário (ex: `christian.silva@netminas.com.br`).
- O sistema criará seu Token automaticamente por baixo dos panos na primeira chamada para `GET /auth/me`. 
*(Nós logo faremos uma telinha nas Configurações onde você poderá clicar para Copiar esse token de forma visual).*

Essa chave deve ser enviada em **todas** as requisições pelo cabeçalho `X-API-Key`.

---

## 2. Especificação do Endpoint

- **URL Base:** `https://inno-fiscal.fly.dev`
- **Endpoint:** `/integracao/receber-venda`
- **Método HTTP:** `POST`
- **Cabeçalhos:**
  - `Content-Type: application/json`
  - `X-API-Key: {SEU_TOKEN_DE_INTEGRACAO}`

### O que o Endpoint aceita?
Payload validado por schema. O `valor_total` da nota é **calculado no servidor** como `Σ(quantidade × valor_unitario) − desconto` — você não precisa (e não deve) enviá-lo.

Campos obrigatórios:
- `cliente.nome` (string)
- `itens` (lista com ao menos 1 item, cada um com `nome`, `quantidade > 0`, `valor_unitario ≥ 0`)

Campos opcionais no topo: `desconto` (≥ 0, default 0), `pagamentos`, `numero_pedido_externo`.
Campos opcionais em `cliente`: `cpf`, `cnpj` (envie um dos dois), e qualquer outro campo (email, endereco, etc.) — extras são preservados no rascunho.

---

## 3. Exemplo Prático de JSON de Venda

```json
{
  "cliente": {
    "nome": "Consumidor Exemplo",
    "cpf": "12345678909"
  },
  "itens": [
    {
      "codigo": "JOIA001",
      "nome": "Anel de Prata Solitário",
      "quantidade": 1,
      "valor_unitario": 150,
      "unidade": "UN"
    },
    {
      "codigo": "JOIA002",
      "nome": "Brinco Ouro 18k Argola",
      "quantidade": 2,
      "valor_unitario": 450,
      "unidade": "PR"
    }
  ],
  "desconto": 50,
  "pagamentos": [
    { "meio_pagamento": "17", "valor": 1000 }
  ]
}
```

Nesse exemplo, o rascunho será criado com `valor_total = (1×150 + 2×450) − 50 = 1000`.

Campos extras (endereço do cliente, e-mail, referência de pedido, timestamps) podem ser adicionados livremente — eles ficam armazenados no rascunho para você revisar na UI.

---

## 4. Testando via Terminal (cURL)

```bash
curl -X POST https://inno-fiscal.fly.dev/integracao/receber-venda \
  -H "Content-Type: application/json" \
  -H "X-API-Key: SuaChaveAqui" \
  -d '{
    "cliente": { "nome": "Consumidor Exemplo", "cpf": "12345678909" },
    "itens": [
      { "codigo": "JOIA001", "nome": "Anel de Prata", "quantidade": 1, "valor_unitario": 150, "unidade": "UN" }
    ],
    "desconto": 0,
    "pagamentos": [ { "meio_pagamento": "17", "valor": 150 } ]
  }'
```

Se tudo der certo, você receberá um **HTTP 200 OK** contendo a estrutura da Nova Nota como resposta (status `rascunho`), que então aparecerá instantaneamente no Painel.
