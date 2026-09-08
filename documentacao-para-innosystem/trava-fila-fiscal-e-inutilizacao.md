# Trava de Fila Fiscal, Denegação, Pendência e Inutilização

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
