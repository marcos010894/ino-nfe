# 07 — Central de Documentos (Etapa E)

> **Objetivo:** criar a tela onde todas as notas emitidas ficam listadas, com filtros,
> e onde é possível baixar XML/PDF, cancelar notas e — o recurso mais valioso —
> **reprocessar notas rejeitadas** sem recolar tudo.

## Pré-requisitos
- [ ] Etapas `05` e `06` concluídas (NFC-e e NF-e emitindo, tabela `notas` populada).

---

## O que vamos construir

### 7.1. Listagem unificada
- Uma tela que mostra **todas as notas** (NF-e e NFC-e) numa única lista.
- **Filtros:** por período (data), por empresa/cliente, por status (autorizada,
  rejeitada, cancelada, processando).
- Colunas úteis: empresa, modelo, número, data, valor, status.

### 7.2. Ações rápidas por nota
Ao selecionar uma nota:
- **Visualizar/Baixar XML**
- **Visualizar/Baixar PDF** (DANFE para NF-e / DANFCE para NFC-e — os "espelhos" impressos)
- **Cancelar nota** — com justificativa obrigatória, respeitando o prazo legal (a
  integradora informa se ainda está no prazo).

### 7.3. ⭐ Reprocessar Erro (o recurso-chave)
- Para notas **rejeitadas**: abrir os dados da nota **na própria tela**, deixar o operador
  **corrigir** o que estava errado (ex: um NCM, um valor), e **reenviar** — **sem precisar
  recolar o JSON da venda**.
- Isso economiza muito tempo: o operador não recomeça do zero, só ajusta e reenvia.

---

## O fluxo do "Reprocessar Erro"

```
1. Nota volta REJEITADA (ex: "NCM inválido")
2. Operador abre a nota na Central de Documentos
3. Vê o motivo do erro em destaque
4. Edita os campos problemáticos direto na tela (os dados já estão lá, do json_venda salvo)
5. Clica "Reenviar"
6. Sistema monta o payload de novo com os dados corrigidos e reenvia
7. Nota atualiza para autorizada (ou rejeitada de novo, se ainda houver erro)
```

> É por isso que salvamos `json_venda` e `resposta_integradora` na tabela `notas` lá na
> etapa 05 — sem esses dados guardados, o reprocessamento seria impossível.

---

## Como pedir para a IA

> "No InnoNFe, quero a Central de Documentos. Já tenho a tabela `notas` com NFC-e e NF-e
> emitidas. Uso a integradora **[NOME]** — documentação de cancelamento e download de
> XML/PDF: [COLE OS TRECHOS]. Preciso:
> 1. Uma tela de listagem unificada de todas as notas, com **filtros** por período,
>    empresa e status, e paginação.
> 2. Ações por nota: baixar/visualizar XML, baixar/visualizar PDF (DANFE/DANFCE).
> 3. **Cancelar nota** com justificativa obrigatória (mínimo de caracteres exigido pela
>    SEFAZ), chamando o cancelamento na integradora e atualizando o status.
> 4. **Reprocessar erro:** para notas rejeitadas, uma tela de edição que carrega os dados
>    salvos (`json_venda`), destaca o motivo do erro, permite corrigir os campos e
>    reenviar — **sem recolar o JSON**. Atualizar a nota após o reenvio.
> Comente o código; mantenha comunicação com a integradora no servidor; homologação."

---

## Critérios de aceite
- [ ] Vejo todas as notas numa lista única.
- [ ] Os filtros por período, empresa e status funcionam.
- [ ] Consigo baixar o XML e o PDF de uma nota autorizada.
- [ ] Consigo cancelar uma nota (com justificativa) dentro do prazo.
- [ ] Consigo pegar uma nota rejeitada, corrigir o dado na tela e reenviar sem recolar o JSON.
- [ ] Depois do reprocessamento, o status da nota atualiza corretamente.

---

## Dicas e armadilhas comuns
- O **cancelamento tem prazo legal** (varia por tipo de nota/estado). A integradora
  costuma recusar fora do prazo — trate essa resposta com uma mensagem clara ao operador.
- A justificativa de cancelamento tem **mínimo de caracteres** (geralmente 15). Valide isso.
- Baixar XML/PDF geralmente é pegar uma URL que a integradora fornece — confirme na doc dela.
- O "reprocessar" é o diferencial da proposta. Capriche na usabilidade: mostre o erro bem
  visível e deixe claro o que precisa ser corrigido.
- Commit no Git ao terminar. ✅
