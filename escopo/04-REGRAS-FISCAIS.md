# 04 — Regras Fiscais (Etapa B)

> **Objetivo:** criar o painel onde se configura como cada empresa calcula os impostos
> das notas. É o "cérebro fiscal" do sistema — o que transforma uma venda crua em uma
> nota fiscal válida.

## Pré-requisitos
- [ ] Etapa `03` concluída (empresas cadastradas).

---

## O que vamos construir

Um painel, **por empresa**, para configurar as **Operações Fiscais** padrão:

- **CFOP** (Código Fiscal de Operações e Prestações) — define o tipo da operação
  (ex: venda dentro do estado, fora do estado).
- **NCM padrão** (Nomenclatura Comum do Mercosul) — código do tipo de produto.
- **ICMS / CSOSN** — o imposto estadual. Empresas do Simples usam CSOSN; outras usam CST/ICMS.
- **PIS** e **COFINS** — impostos federais.

A ideia do MVP é ter uma **parametrização base**: valores padrão que serão aplicados na
hora de emitir a nota. Não precisa cobrir todos os casos fiscais do Brasil — só o
suficiente pro varejo de joias/semijoias descrito na proposta.

> 💡 **Importante:** você não precisa ser contador. Peça as regras corretas ao contador
> da(s) loja(s) — CFOP, CST/CSOSN, NCM e alíquotas são informações que o contador fornece.
> O sistema só precisa **guardar e aplicar** o que ele definir.

---

## Modelo de dados

```
regras_fiscais
├── id
├── empresa_id
├── nome            # ex: "Venda de joia - dentro do estado"
├── cfop
├── ncm_padrao
├── origem_icms     # 0 a 8 (origem da mercadoria)
├── cst_csosn       # CST (ICMS) ou CSOSN (Simples)
├── icms_aliquota
├── pis_cst, pis_aliquota
├── cofins_cst, cofins_aliquota
├── padrao          # se é a regra padrão da empresa (sim/não)
├── criado_em
```

> Uma empresa pode ter **várias** regras (ex: uma pra venda no estado, outra pra fora).
> Marque uma como "padrão".

---

## Como pedir para a IA

> "No InnoNFe, quero um módulo de Regras Fiscais, configurável **por empresa**. Preciso:
> 1. Criar a tabela `regras_fiscais` com **SQLModel** e gerar a migration com Alembic. [cole os campos acima]
> 2. Uma tela dentro do cadastro da empresa para listar/criar/editar/excluir regras fiscais.
> 3. Campos: nome da regra, CFOP, NCM padrão, origem do ICMS, CST/CSOSN, alíquota de ICMS,
>    CST e alíquota de PIS, CST e alíquota de COFINS, e uma marcação de 'regra padrão'.
> 4. Validações básicas (ex: CFOP tem 4 dígitos, NCM tem 8 dígitos).
> Não precisa calcular impostos automaticamente ainda — só guardar as regras. Use shadcn/ui."

---

## Critérios de aceite
- [ ] Consigo abrir uma empresa e ver suas regras fiscais.
- [ ] Consigo criar uma nova regra com todos os campos.
- [ ] Consigo editar e excluir regras.
- [ ] Consigo marcar uma regra como "padrão".
- [ ] As validações básicas de formato funcionam (CFOP, NCM).

---

## Dicas e armadilhas comuns
- **Não invente alíquotas.** Use valores fornecidos por um contador. Para testar, pode
  usar valores fictícios, mas deixe claro que são de teste.
- No MVP, mantenha simples. A tentação de cobrir todo o sistema tributário brasileiro é
  grande — resista. O objetivo é validar o fluxo, não virar um ERP fiscal completo.
- Essas regras serão **usadas** na próxima etapa (emissão). Aqui só as guardamos.
- Commit no Git ao terminar. ✅
