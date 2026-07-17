# 06 — Emissão de NF-e (Etapa D)

> **Objetivo:** emitir a **NF-e (modelo 55)** — a nota fiscal "completa" (entre empresas,
> transporte de mercadoria, etc.). A diferença técnica principal para a NFC-e é que ela é
> **assíncrona**: você envia e depois precisa **consultar o status** até a SEFAZ responder.

## Pré-requisitos
- [ ] Etapa `05` (NFC-e) concluída e funcionando. O grosso da estrutura já existe;
      aqui a gente adapta.

---

## O que vamos construir

### 6.1. Botão "Emitir NF-e (modelo 55)"
Na mesma tela "Emitir Nota", um botão para emitir NF-e. O fluxo reaproveita quase tudo da
NFC-e (colar JSON, prévia, regras fiscais), mas muda o **modelo** (55) e o **modo de envio**.

### 6.2. Envio assíncrono + controle de status (polling)
- Ao emitir, a integradora aceita o pedido e devolve um "está processando".
- O sistema **não** trava esperando. Ele salva a nota como **"processando"**.
- Depois, o sistema **consulta o status** de tempos em tempos (isso se chama *polling*),
  até virar **autorizada** ou **rejeitada**.
- A tela mostra o status atualizando (ex: "Processando..." → "Autorizada ✅").

> **Assíncrono / polling** = você manda, ela diz "vou processar", e você fica perguntando
> "já ficou pronto?" até ela responder. É como pedir comida e acompanhar o status do pedido.

---

## O fluxo por dentro

```
1. Operador cola o JSON e clica "Emitir NF-e"
2. Sistema monta o payload (modelo 55) e envia à integradora
3. Integradora responde "processando" + um identificador (referência)
4. Sistema salva a nota com status "processando"
5. De tempos em tempos, o sistema consulta o status pela referência
6. Quando virar autorizada/rejeitada, atualiza a nota e a tela
```

### Ajuste no modelo de dados
A tabela `notas` (criada na etapa 05) já serve. Talvez precise de um campo extra:
```
notas
├── ...
├── referencia_integradora   # identificador para consultar status depois
├── ...
```

### Como fazer o polling (opções, da mais simples à mais robusta)
1. **Simples (MVP):** um botão "Atualizar status" que o operador clica, ou a tela consulta
   automaticamente a cada X segundos enquanto estiver aberta.
2. **Melhor:** uma consulta automática em segundo plano. Para o MVP, a opção 1 já resolve.

> Comece pela opção simples. Não complique o MVP com filas e servidores de background
> antes de ter o fluxo básico funcionando.

---

## Como pedir para a IA

> "No InnoNFe, já tenho a emissão de NFC-e (modelo 65) funcionando. Agora quero adicionar
> a emissão de **NF-e (modelo 55)**, que é **assíncrona**. Uso a integradora
> **[NOME]** — documentação: [COLE OS TRECHOS SOBRE NF-e E CONSULTA DE STATUS].
> Preciso:
> 1. Adicionar o botão 'Emitir NF-e (modelo 55)' na tela 'Emitir Nota', reaproveitando a
>    lógica de colar JSON, prévia e regras fiscais.
> 2. Uma rota de API que envia a NF-e à integradora (homologação) e salva a nota como
>    'processando', guardando a referência para consultar depois.
> 3. Uma rota de API que **consulta o status** de uma nota pela referência e atualiza o
>    banco (autorizada/rejeitada + motivo).
> 4. Na tela, mostrar o status atualizando — comece com um botão 'Atualizar status' e/ou
>    consulta automática a cada 10s enquanto a nota estiver 'processando'.
> Comente o código e mantenha tudo em homologação."

---

## Critérios de aceite
- [ ] Consigo emitir uma NF-e (modelo 55) que fica com status "processando".
- [ ] O sistema consulta o status e atualiza para "autorizada" ou "rejeitada".
- [ ] A tela reflete a mudança de status.
- [ ] O motivo da rejeição aparece quando for o caso.
- [ ] A NFC-e (etapa 05) continua funcionando normalmente.

---

## Dicas e armadilhas comuns
- Não deixe a nota presa em "processando" pra sempre. Garanta que existe um jeito de
  reconsultar (botão ou automático).
- NF-e tem mais campos obrigatórios que NFC-e (ex: dados do destinatário/comprador). O
  JSON de venda para NF-e provavelmente precisa de mais informações — ajuste o formato.
- Rejeições continuam sendo normais em teste. A etapa 07 resolve o "reprocessar".
- Commit no Git ao terminar. ✅
