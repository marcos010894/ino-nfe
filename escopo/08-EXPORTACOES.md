# 08 — Exportações e Download em Lote (Etapa F)

> **Objetivo:** permitir baixar várias notas de uma vez, num arquivo ZIP contendo os
> XMLs e/ou PDFs (DANFE/DANFCE). É o que a contabilidade normalmente pede no fim do mês.

## Pré-requisitos
- [ ] Etapa `07` (Central de Documentos) concluída, com filtros funcionando.

---

## O que vamos construir

- Na Central de Documentos (etapa 07), após aplicar os filtros (período, empresa, status),
  um botão **"Baixar em lote"**.
- Ele gera um arquivo **ZIP** contendo os XMLs e/ou PDFs de **todas as notas filtradas**.
- Opção de escolher o que incluir: só XML, só PDF, ou ambos.

> Este é o mais simples dos módulos, e por isso fica por último. Ele apenas reúne
> arquivos que já existem (gerados nas etapas anteriores) e os empacota.

---

## O fluxo por dentro

```
1. Operador filtra as notas (ex: empresa X, mês de janeiro, autorizadas)
2. Clica "Baixar em lote"
3. Servidor busca os XMLs/PDFs de cada nota (das URLs da integradora ou do que foi salvo)
4. Servidor monta um arquivo ZIP com todos
5. O ZIP é enviado para download
```

---

## Como pedir para a IA

> "No InnoNFe, na Central de Documentos, quero adicionar 'Baixar em lote'. Preciso:
> 1. Um botão que, respeitando os filtros aplicados na listagem, baixa todas as notas
>    filtradas.
> 2. Uma opção para escolher: incluir XML, PDF (DANFE/DANFCE) ou ambos.
> 3. Uma rota de API no servidor que busca os arquivos de cada nota, monta um ZIP (ex:
>    com o módulo `zipfile` do Python) e retorna para download (StreamingResponse).
> 4. Um nome de arquivo claro no ZIP (ex: `notas_[empresa]_[periodo].zip`) e nomes
>    organizados por nota dentro dele (ex: usar a chave de acesso).
> 5. Um indicador de carregamento, já que muitos arquivos podem demorar.
> Comente o código; faça o empacotamento no servidor."

---

## Critérios de aceite
- [ ] Consigo filtrar notas e clicar "Baixar em lote".
- [ ] Recebo um arquivo ZIP com os XMLs e/ou PDFs corretos.
- [ ] Consigo escolher incluir só XML, só PDF ou ambos.
- [ ] Os arquivos dentro do ZIP têm nomes que dá pra identificar.

---

## Dicas e armadilhas comuns
- Se houver **muitas** notas, gerar o ZIP pode demorar ou pesar. Para o MVP, tudo bem;
  se virar problema no futuro, dá pra limitar a quantidade por download.
- Cuide dos casos em que uma nota **não** tem XML/PDF (ex: rejeitada) — pule ou avise.
- Commit no Git ao terminar. ✅

---

# 🎉 Fim do MVP!

Se você chegou até aqui com todos os critérios de aceite marcados, o **InnoNFe Fase 1**
está completo. Próximos passos possíveis:

- Testar bastante em **homologação** com casos reais.
- Pedir a um **contador** para validar as regras fiscais e uma nota emitida.
- Só então planejar a migração para **produção** (com muito cuidado — nota fiscal real
  tem valor legal).
- Depois, olhar os itens da **Fase 2** (ver `00-COMECE-AQUI.md`, seção 4).

Parabéns pelo projeto! 🚀
