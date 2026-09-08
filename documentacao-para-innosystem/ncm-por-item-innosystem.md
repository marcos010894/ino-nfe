# NCM por Item — Integração InnoSystem

**Ambiente:** `https://inno-fiscal.fly.dev`
**Token:** o mesmo `X-API-Key` da integração `/receber-venda`.

O InnoSystem pode mandar o `ncm` do produto no JSON da venda. Se vier, o InnoFiscal usa. Se não vier, cai no `ncm_padrao` da regra fiscal da empresa.

---

## Regra

| InnoSystem manda `ncm` no item? | NCM usado na NF-e / NFC-e                            |
|---------------------------------|------------------------------------------------------|
| Sim                             | O que veio no item                                   |
| Não (campo ausente)             | `ncm_padrao` da regra fiscal padrão da empresa       |
| String vazia (`""`)             | `ncm_padrao` da regra fiscal padrão da empresa       |

A regra vale nos 2 endpoints que aceitam o payload de venda:

- `POST /integracao/receber-venda`
- `POST /integracao/reenviar/{nota_id}`

---

## Campo no payload

Novo campo opcional dentro de cada item de `itens`:

```json
{
  "cliente": { "nome": "ALINE SILVA DA COSTA", "cpf": "73846720828" },
  "itens": [
    {
      "codigo": "216685",
      "nome": "TRIO DE BRINCOS DE PEROLAS B. OURO",
      "quantidade": 3,
      "valor_unitario": 119.00,
      "unidade": "UN",
      "ncm": "71171900"
    },
    {
      "codigo": "216686",
      "nome": "PULSEIRA PRATA",
      "quantidade": 1,
      "valor_unitario": 250.00,
      "unidade": "UN"
    }
  ],
  "desconto": 0,
  "pagamentos": [ { "meio_pagamento": "01", "valor": 607.00 } ]
}
```

No exemplo:

- Item `216685` → sai com NCM `71171900` (veio no payload).
- Item `216686` → sai com o `ncm_padrao` da empresa (não veio no payload).

---

## Formato aceito

| Formato       | Aceito? | Vira      |
|---------------|:-------:|-----------|
| `"71171900"`  | Sim     | `71171900`|
| `"7117.19.00"`| Sim     | `71171900`|
| `"7117 19 00"`| Sim     | `71171900`|
| `71171900`    | Sim     | `71171900`|

Backend limpa qualquer caractere não numérico e usa os primeiros 8 dígitos.

Se depois da limpeza sobrarem menos de 8 dígitos, a SEFAZ rejeita a nota (o InnoFiscal transmite mesmo assim — a rejeição vem por cStat da SEFAZ, não como validação local).

---

## Exemplo curl

```bash
curl -X POST "https://inno-fiscal.fly.dev/integracao/receber-venda" \
  -H "X-API-Key: SEU_TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente": { "nome": "ALINE SILVA DA COSTA", "cpf": "73846720828" },
    "itens": [
      {
        "codigo": "216685",
        "nome": "TRIO DE BRINCOS",
        "quantidade": 3,
        "valor_unitario": 119.00,
        "ncm": "71171900"
      }
    ],
    "desconto": 0,
    "pagamentos": [ { "meio_pagamento": "01", "valor": 357.00 } ]
  }'
```

---

## NCMs recomendados (autocomplete do InnoFiscal)

Mesma lista que aparece como sugestão na tela de Regra Fiscal do InnoFiscal (input `NCM Padrão`). Serve como referência pro InnoSystem alinhar os NCMs cadastrados por produto:

| NCM        | Descrição                                       |
|------------|-------------------------------------------------|
| `71131900` | Joias de ouro / outros metais preciosos         |
| `71131100` | Joias de prata                                  |
| `71132000` | Semijoias (metal comum folheado / plaquê)       |
| `71171900` | Bijuterias de metal comum                       |
| `71179000` | Bijuterias (outras)                             |
| `91011100` | Relógios de pulso — caixa de metal precioso     |
| `91021100` | Relógios de pulso — outros                      |
| `85171300` | Smartphones                                     |
| `85171400` | Celulares (outros)                              |
| `85176294` | Fones de ouvido / headsets                      |
| `84713012` | Tablets                                         |
| `85444200` | Cabos USB / dados                               |
| `85287200` | Televisores                                     |
| `42021200` | Bolsas / carteiras (material sintético)         |
| `61091000` | Camisetas / t-shirts (algodão)                  |

Não é lista exclusiva — o InnoSystem pode mandar qualquer NCM válido (8 dígitos). A lista acima é só sugestão pra facilitar o cadastro.

---

## Onde está no Swagger

`https://inno-fiscal.fly.dev/docs` → schema `ReceberVendaItem` → campo `ncm` opcional.
