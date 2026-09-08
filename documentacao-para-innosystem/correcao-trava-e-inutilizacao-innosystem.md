# Correção, Trava de Fila e Inutilização — Integração InnoSystem

**Ambiente:** `https://inno-fiscal.fly.dev` · **Token:** `X-API-Key` do usuário do InnoFiscal.

Dois blocos: (1) correção de nota rejeitada via `/reenviar`, (2) trava HTTP 422 + denegação + `pendente_consulta` + inutilização por id.

---

## Correção e Reenvio de Nota Rejeitada — Integração InnoSystem

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

---

## Trava de Fila Fiscal, Denegação, Pendência e Inutilização

**Ambiente:** `https://inno-fiscal.fly.dev`
**Token:** o mesmo `X-API-Key` da integração `/receber-venda`.

Regras adicionadas ao fluxo pra proteger a sequência de `nNF` na SEFAZ:

- `/receber-venda` recusa nova venda se existe nota pendente (rejeitada ou timeout).
- Denegação SEFAZ (cStat 110/301/302) vira status próprio — não pode reenviar.
- Timeout na SEFAZ marca a nota como `pendente_consulta` — precisa consultar antes de decidir.
- Nota rejeitada/pendente pode ser inutilizada por `id` — destrava a fila.

---

## Status novos

| Status              | O que significa                                                       | InnoSystem faz                                       |
|---------------------|-----------------------------------------------------------------------|------------------------------------------------------|
| `denegada`          | SEFAZ recusou permanentemente (cStat 110/301/302). `nNF` foi consumido.| Nada. Próxima venda usa `nNF+1`.                     |
| `pendente_consulta` | Timeout de comunicação. SEFAZ pode ter recebido ou não.                | Chama `POST /notas/{id}/consultar` até resolver.     |
| `inutilizada`       | Operador desistiu — `nNF` queimado na SEFAZ.                           | Nada. Próxima venda usa `nNF+1`.                     |

Status `rejeitada` (existente) e `pendente_consulta` **travam a fila**. Os outros não.

---

## 1. Trava no `POST /integracao/receber-venda`

Se o usuário do `X-API-Key` tem alguma nota anterior com `status="rejeitada"` ou `status="pendente_consulta"`, o endpoint recusa a nova venda:

**HTTP 422**

```json
{
  "sucesso": false,
  "tipo_erro": "ERRO_INTERNO_REGRA_FISCAL",
  "codigo_erro": "PENDENCIA_NOTA_ANTERIOR",
  "mensagem": "Não foi possível emitir a nova nota fiscal. Existe uma nota fiscal anterior (ID: 1706, Número: 10) que foi rejeitada pela SEFAZ e precisa ser corrigida/retransmitida antes de prosseguir.",
  "detalhes": {
    "id_nota_pendente": 1706,
    "numero_nota_pendente": 10,
    "status_atual": "rejeitada"
  }
}
```

**O que fazer:** resolver a nota apontada em `detalhes.id_nota_pendente` (reenviar corrigido, consultar, ou inutilizar) antes de reenviar a venda nova.

---

## 2. Denegação (cStat 110 / 301 / 302)

Quando a SEFAZ denega, o InnoFiscal marca `status="denegada"` (em vez de `"rejeitada"`).

**Diferenças pra rejeitada:**

| Comportamento              | `rejeitada`               | `denegada`                       |
|----------------------------|---------------------------|----------------------------------|
| `nNF` consumido?           | Não                       | Sim                              |
| Aceita reenvio?            | Sim (`POST /reenviar/`)   | Não                              |
| Trava a fila?              | Sim                       | Não (próxima venda usa `nNF+1`)  |

**Response típica ao consultar `GET /integracao/notas/{id}`:**

```json
{
  "id": 1706,
  "status": "denegada",
  "numero": 10,
  "codigo_status": "110",
  "motivo_status": "Uso Denegado"
}
```

O InnoSystem não faz nada — a fila já está destravada. Se tentar chamar `/reenviar/{id}` numa denegada, o InnoFiscal responde 400.

---

## 3. Timeout → `pendente_consulta`

Quando o InnoFiscal perde conexão com a SEFAZ durante o envio, a nota fica `status="pendente_consulta"`. Não dá pra assumir rejeitada — a SEFAZ pode ter recebido e autorizado. Precisa consultar.

### `POST /integracao/notas/{nota_id}/consultar`

**Headers:**

| Header      | Valor                          |
|-------------|--------------------------------|
| `X-API-Key` | Token do usuário do InnoFiscal |

**Body:** nenhum.

**Response:**

```json
{
  "id": 1706,
  "status": "autorizada",
  "modelo": "65",
  "numero": 10,
  "serie": 1,
  "chave_acesso": "35260815278447000102650010000000101...",
  "valor_total": 357.00,
  "xml_url": "/integracao/notas/1706/xml",
  "pdf_url": "/integracao/notas/1706/pdf"
}
```

**Status possíveis no retorno:**

| `status`             | O que aconteceu                                     | Próxima ação do InnoSystem                        |
|----------------------|-----------------------------------------------------|---------------------------------------------------|
| `autorizada`         | SEFAZ autorizou                                     | Nada. Fila destrava.                              |
| `rejeitada`          | SEFAZ rejeitou                                      | `POST /reenviar/{id}` com JSON corrigido          |
| `denegada`           | SEFAZ denegou                                       | Nada. Fila destrava.                              |
| `pendente_consulta` | SEFAZ ainda não decidiu / não recebeu o payload      | Chamar `/consultar` de novo depois de alguns min  |

Idempotente — chamar em nota já autorizada/rejeitada devolve o estado atual sem consultar de novo.

---

## 4. Inutilização por `id` (último recurso)

Quando o operador **desiste da venda rejeitada/pendente** e não vai reenviar, o `nNF` reservado pode ser inutilizado na SEFAZ pra destravar a fila.

Preferência: sempre reenviar corrigido antes. Só inutilizar se a venda foi realmente descartada.

### `POST /integracao/inutilizar/{nota_id}`

**Headers:**

| Header      | Valor                          |
|-------------|--------------------------------|
| `X-API-Key` | Token do usuário do InnoFiscal |

**Body:**

```json
{
  "justificativa": "Cliente desistiu da compra antes da autorizacao"
}
```

`justificativa` precisa de no mínimo 15 caracteres.

**Response (sucesso):**

```json
{
  "sucesso": true,
  "nota_id": 1706,
  "numero_inutilizado": 10,
  "modelo": "65",
  "serie": 1,
  "resposta_sefaz": { "...": "..." }
}
```

A nota vira `status="inutilizada"`, a fila destrava, próxima venda usa `nNF+1`.

**Erros esperados:**

| HTTP | Motivo                                                        |
|------|---------------------------------------------------------------|
| 400  | `status` não é `rejeitada` nem `pendente_consulta`            |
| 400  | Nota sem `numero` reservado                                    |
| 400  | Nota sem `empresa_id` vinculada                                |
| 400  | Justificativa com menos de 15 caracteres                       |
| 400  | SEFAZ recusou a inutilização (mensagem inclui `cStat` original)|
| 404  | `nota_id` não pertence ao usuário do `X-API-Key`               |

---

## Fluxo completo — decisão do InnoSystem

```
POST /receber-venda
       │
       ├── 422 PENDENCIA_NOTA_ANTERIOR
       │    └─► Ir pra nota pendente indicada em `detalhes.id_nota_pendente`
       │
       └── 200 nota criada
              │
              ├── GET /notas/{id}  → status="autorizada"        → OK, próxima venda
              │
              ├── GET /notas/{id}  → status="rejeitada"         → POST /reenviar/{id} com JSON corrigido
              │                                                      OU POST /inutilizar/{id} se desistir
              │
              ├── GET /notas/{id}  → status="denegada"          → Nada. Próxima venda pega nNF+1
              │
              ├── GET /notas/{id}  → status="pendente_consulta" → POST /notas/{id}/consultar
              │                                                    ├── volta "autorizada" → OK
              │                                                    ├── volta "rejeitada"  → /reenviar ou /inutilizar
              │                                                    └── volta "pendente"   → tenta de novo depois
              │
              └── GET /notas/{id}  → status="inutilizada"       → Nada. Próxima venda pega nNF+1
```

---

## Exemplos curl

**Consultar nota pendente:**

```bash
curl -X POST "https://inno-fiscal.fly.dev/integracao/notas/1706/consultar" \
  -H "X-API-Key: SEU_TOKEN_AQUI"
```

**Inutilizar nota rejeitada:**

```bash
curl -X POST "https://inno-fiscal.fly.dev/integracao/inutilizar/1706" \
  -H "X-API-Key: SEU_TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{ "justificativa": "Cliente desistiu da compra antes da autorizacao" }'
```
