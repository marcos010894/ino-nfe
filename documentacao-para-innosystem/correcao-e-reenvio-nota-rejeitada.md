# Correção e Reenvio de Nota Rejeitada

**Ambiente:** `https://inno-fiscal.fly.dev`
**Token:** o mesmo `X-API-Key` da integração `/receber-venda`.

Fluxo para reaproveitar o `nNF` de uma nota rejeitada pela SEFAZ, evitando furo na sequência de numeração.

---

## Fluxo

```
┌──────────────┐    1. Emite venda        ┌──────────────┐
│  InnoSystem  │ ───────────────────────► │  InnoFiscal  │
└──────────────┘                          └──────┬───────┘
                                                 │
                                                 │ 2. Transmite pra SEFAZ
                                                 ▼
                                          ┌──────────────┐
                                          │    SEFAZ     │
                                          └──────┬───────┘
                                                 │
                                                 │ 3. Retorna REJEIÇÃO (ex: cStat 866)
                                                 ▼
                                          ┌──────────────┐
                                          │  InnoFiscal  │  nota fica salva com:
                                          │              │  - status = "rejeitada"
                                          │              │  - numero = 10
                                          │              │  - serie  = 1
                                          │              │  - motivo_status = "cStat 866..."
                                          └──────┬───────┘
                                                 │
                                                 │ 4. Operador abre a nota (SSO)
                                                 ▼
                                          ┌──────────────┐
                                          │  Tela /emitir│  botão "Corrigir e reenviar"
                                          │  (rejeitada) │  campos de destinatário editáveis
                                          └──────┬───────┘
                                                 │
                                                 │ 5. Operador corrige + clica reenviar
                                                 ▼
                                          ┌──────────────┐
                                          │  InnoFiscal  │  reusa nNF = 10, remonta payload
                                          └──────┬───────┘
                                                 │
                                                 │ 6. Transmite pra SEFAZ
                                                 ▼
                                          ┌──────────────┐
                                          │    SEFAZ     │  AUTORIZADA (Status 100)
                                          └──────────────┘
                                                 │
                                                 │ 7. Próxima venda usa nNF = 11
                                                 ▼
```

---

## Comportamento do `nNF`

| Evento                                    | `nNF` da nota | Próxima venda |
|-------------------------------------------|---------------|---------------|
| Venda emitida, SEFAZ rejeita              | 10 (fica no banco) | usa 10 no reenvio |
| Reenvio autorizado                        | 10 (autorizada)    | 11            |
| Reenvio rejeitado de novo                 | 10 (rejeitada)     | usa 10 no próximo reenvio |
| Operador desiste e exclui a venda         | 10 (a inutilizar)  | 11 (número 10 vai pra fila de Inutilização) |

Regra: o `nNF` **nunca** é incrementado enquanto a nota estiver rejeitada. Só avança quando a nota vira **autorizada**, **cancelada** ou **inutilizada** na SEFAZ.

---

## O que o InnoSystem faz

**Correção de dados do destinatário** (endereço, telefone, e-mail) — nada. Operador arruma direto no InnoFiscal.

**Correção de produto/valor/quantidade** — operador clica em "Excluir venda e refazer no InnoSystem" na tela do InnoFiscal, o rascunho é apagado, o InnoSystem volta a permitir edição da venda. Depois é só emitir de novo via `/integracao/receber-venda` como qualquer venda nova.

Não há endpoint novo pra chamar. O SSO existente (`POST /integracao/sessao` → `/sso?token=...&rascunho=...`) já cobre o acesso à tela de correção.

---

## O que o InnoFiscal faz

### Endpoint de reenvio (interno da tela)

```
POST https://inno-fiscal.fly.dev/notas/{id}/reenviar
```

**Headers:**

| Header          | Valor                          |
|-----------------|--------------------------------|
| `Authorization` | `Bearer <JWT do operador>`     |

**Body (opcional):**

```json
{
  "destinatario": {
    "nome": "ALINE SILVA DA COSTA",
    "cpf_cnpj": "738.467.208-28",
    "logradouro": "CORONEL DUARTE",
    "numero": "7",
    "bairro": "CENTRO",
    "municipio": "Rio Bonito",
    "uf": "RJ",
    "cep": "28800000",
    "telefone": "22999999999",
    "email": "alinesilva@outlook.com"
  }
}
```

Se o body for vazio, o InnoFiscal reusa o `json_venda` salvo e apenas retransmite.

**Regras:**

- Só aceita nota com `status = "rejeitada"`.
- Reusa `numero` e `serie` da nota original.
- Substitui o registro existente (não cria nota nova).
- Retorna o mesmo shape de `POST /notas` (status + resposta ACBr).

**Response (autorizada):**

```json
{
  "id": 1706,
  "status": "autorizada",
  "numero": 10,
  "serie": 1,
  "chave_acesso": "35260815278447000102650010000000101...",
  "modelo": "65",
  "pdf_url": "/empresas/1/notas/1706/pdf",
  "xml_url": "/empresas/1/notas/1706/xml"
}
```

**Response (rejeitada de novo):**

```json
{
  "id": 1706,
  "status": "rejeitada",
  "numero": 10,
  "serie": 1,
  "codigo_status": 866,
  "motivo_status": "Rejeicao: Ausencia de troco quando o valor dos pagamentos..."
}
```

### UI da tela `/emitir`

Quando a nota está com `status = "rejeitada"`:

- Banner vermelho no topo com `codigo_status` + `motivo_status`.
- Campos de destinatário (nome, endereço, telefone, e-mail) editáveis.
- Botão azul: **Corrigir e reenviar** → chama `POST /notas/{id}/reenviar`.
- Botão vermelho (existente): **Excluir venda e refazer no InnoSystem**.

Produto/valor/quantidade continuam read-only nessa tela — se precisar mudar, é pelo botão vermelho.

---

## Casos de uso

| Situação                                             | Ação do operador                                         | Reaproveita `nNF`? |
|------------------------------------------------------|----------------------------------------------------------|--------------------|
| CEP do cliente inválido (cStat 610)                  | Edita CEP na tela → Corrigir e reenviar                  | Sim                |
| Endereço obrigatório faltando (cStat 726)            | Preenche endereço → Corrigir e reenviar                  | Sim                |
| Pagamento maior que total da nota (cStat 866)        | Excluir venda → corrigir no InnoSystem → reemitir        | Não (número inutilizado depois) |
| Produto sem descrição (cStat 228)                    | Excluir venda → corrigir no InnoSystem → reemitir        | Não                |
| Cliente desistiu da compra                           | Excluir venda                                            | Não (número inutilizado depois) |

---

## Regra de ouro

Nenhum `nNF` gerado desaparece. Todo número precisa constar na SEFAZ como uma destas três:

- **Autorizada** (Status 100)
- **Cancelada** (após autorização)
- **Inutilizada** (evento de inutilização)

O InnoFiscal garante isso mantendo o `nNF` no banco enquanto a nota estiver rejeitada e enfileirando pra inutilização quando o operador desiste da venda.
