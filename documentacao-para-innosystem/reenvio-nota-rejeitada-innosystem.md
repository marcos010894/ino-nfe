# Correção e Reenvio de Nota Rejeitada — Integração InnoSystem

**Ambiente:** `https://inno-fiscal.fly.dev`
**Token:** o mesmo `X-API-Key` da integração `/receber-venda`.

Quando a SEFAZ rejeita, o InnoSystem manda o JSON corrigido apontando pra nota rejeitada. O InnoFiscal reusa o mesmo `nNF` e retransmite. Nenhum número desaparece da sequência.

---

## Fluxo

1. **InnoSystem envia a venda.** `POST /integracao/receber-venda` → InnoFiscal cria a nota e retorna `id` (ex: `1706`). Guarde esse `id`.
2. **InnoFiscal transmite pra SEFAZ.** A SEFAZ rejeita — a nota fica com `status="rejeitada"`, `numero=10`, `motivo_status="..."`. O `id` continua `1706`.
3. **InnoSystem detecta a rejeição no poll.** `GET /integracao/notas?status=rejeitada` (ou `GET /integracao/notas/1706`) retorna o motivo e o `codigo_status`.
4. **Operador corrige o cadastro/venda no InnoSystem.**
5. **InnoSystem manda o JSON corrigido.** `POST /integracao/reenviar/1706` com o mesmo body do `/receber-venda`.
6. **InnoFiscal retransmite pra SEFAZ reusando `nNF=10`.**
7. **Resposta síncrona.** O próprio `POST /reenviar` já retorna `status="autorizada"` (ou rejeitada de novo, se ainda houver problema) com `chave_acesso`, `xml_url` e `pdf_url`.

O `id` é fixo do início ao fim (`1706` no exemplo). Só o `status` muda.

---

## Endpoint

```
POST https://inno-fiscal.fly.dev/integracao/reenviar/{nota_id}
```

**Headers:**

| Header      | Valor                          |
|-------------|--------------------------------|
| `X-API-Key` | Token do usuário do InnoFiscal |

**Path param:**

| Param     | Descrição                                          |
|-----------|----------------------------------------------------|
| `nota_id` | ID da nota **rejeitada** retornada anteriormente. |

**Body:** mesmo shape do `POST /integracao/receber-venda`.

```json
{
  "cliente": {
    "nome": "ALINE SILVA DA COSTA",
    "cpf": "73846720828",
    "endereco": {
      "logradouro": "CORONEL DUARTE",
      "numero": "7",
      "bairro": "CENTRO",
      "cidade": "Rio Bonito",
      "uf": "RJ",
      "cep": "28800000"
    }
  },
  "itens": [
    {
      "codigo": "216685",
      "nome": "TRIO DE BRINCOS DE PEROLAS B. OURO",
      "quantidade": 3,
      "valor_unitario": 119.00,
      "unidade": "UN",
      "ncm": "71171900"
    }
  ],
  "desconto": 0,
  "pagamentos": [
    { "meio_pagamento": "01", "valor": 357.00 }
  ]
}
```

Você **substitui** o JSON inteiro — não é patch parcial. Manda o venda corrigida do zero.

**Campo `ncm` opcional por item.** Se vier, o InnoFiscal usa o NCM do produto. Se omitir, cai no `ncm_padrao` da regra fiscal da empresa. Aceita com ou sem formatação (`"71171900"` ou `"7117.19.00"`).

---

## Response

**Sucesso (autorizada):**

```json
{
  "id": 1706,
  "status": "autorizada",
  "modelo": "65",
  "numero": 10,
  "serie": 1,
  "chave_acesso": "35260815278447000102650010000000101...",
  "valor_total": 357.00,
  "xml_url": "/empresas/1/notas/1706/xml",
  "pdf_url": "/empresas/1/notas/1706/pdf"
}
```

Mesmo `id` e mesmo `numero` da nota rejeitada. Só o status mudou.

**Rejeitada de novo:**

```json
{
  "id": 1706,
  "status": "rejeitada",
  "numero": 10,
  "codigo_status": 866,
  "motivo_status": "Rejeicao: ..."
}
```

Pode chamar `POST /integracao/reenviar/{nota_id}` de novo quantas vezes precisar — o `nNF` continua reservado.

---

## Erros esperados

| HTTP | Motivo |
|------|--------|
| 400  | `status != "rejeitada"` (só rejeitadas são reenviáveis) |
| 400  | Nota sem `numero` reservado (nunca foi transmitida — use `/receber-venda`) |
| 400  | Nota sem `empresa_id` (idem) |
| 400  | Empresa sem regra fiscal cadastrada |
| 404  | `nota_id` não pertence ao usuário do `X-API-Key` |
| 502  | Falha de comunicação com a ACBr / SEFAZ (não é rejeição fiscal — é infra) |

---

## Comportamento do `nNF`

| Evento                        | `nNF` |
|-------------------------------|-------|
| SEFAZ rejeita                 | 10 (reservado) |
| Reenvio autorizado            | 10 (autorizada) |
| Reenvio rejeitado             | 10 (reservado, pode reenviar de novo) |

Outras vendas emitidas em paralelo pegam o próximo número (11, 12, ...) — a nota 10 não trava o caixa.

---

## Exemplo curl

```bash
curl -X POST "https://inno-fiscal.fly.dev/integracao/reenviar/1706" \
  -H "X-API-Key: SEU_TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente": { "nome": "ALINE SILVA DA COSTA", "cpf": "73846720828" },
    "itens": [
      { "codigo": "216685", "nome": "TRIO DE BRINCOS", "quantidade": 3, "valor_unitario": 119.00 }
    ],
    "desconto": 0,
    "pagamentos": [ { "meio_pagamento": "01", "valor": 357.00 } ]
  }'
```
