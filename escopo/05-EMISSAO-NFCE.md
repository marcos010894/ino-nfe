# 05 — Emissão de NFC-e (Etapa C)

> **Objetivo:** construir a tela "Emitir Nota" e fazer o sistema realmente emitir uma
> **NFC-e (modelo 65)** — a nota do consumidor final, aquela do cupom fiscal. Esta é a
> etapa mais importante do MVP: aqui o sistema deixa de ser "cadastro" e vira "emissor".

## Pré-requisitos
- [ ] Etapas `03` (empresas + certificado) e `04` (regras fiscais) concluídas.
- [ ] **Conta numa integradora fiscal** criada, em ambiente de **homologação** (teste).

---

## ⚠️ ANTES DE TUDO: escolha a integradora fiscal

Você **não** fala direto com a SEFAZ. Você usa uma integradora, que faz a parte difícil
(XML, assinatura com o certificado, comunicação com cada estado). A proposta cita três:

| Integradora | Observação |
|---|---|
| **Focus NFe** | Muito usada, documentação boa, popular em projetos com IA |
| **Nuvem Fiscal** | API moderna, boa documentação |
| **PlugNotas** | Também comum no mercado |

**Como escolher:** entre nos sites das três, veja qual documentação você entende melhor e
qual tem plano de teste (homologação) gratuito. Todas resolvem o problema. Depois de
escolher, **leia a documentação da API dela** — é o que a IA vai usar como referência.

> 💡 Ao pedir pra IA, **cole trechos da documentação da integradora escolhida**. Isso
> deixa o código muito mais certeiro do que a IA "adivinhar" a API.

---

## O que vamos construir

### 5.1. Tela "Emitir Nota" — a "Ponte de Dados (Copia e Cola)"
- Uma área de texto onde o operador **cola o JSON** da venda (gerado pelo InnoSystem).
- Ao colar, o sistema **mostra uma prévia estruturada**: itens, quantidades, valores,
  formas de pagamento — para o operador conferir antes de emitir.
- O sistema **aplica as regras fiscais** da empresa (da Etapa 04) e monta o payload
  (os dados no formato que a integradora espera).

### 5.2. Botão "Emitir NFC-e (modelo 65)"
- Envio **síncrono**: manda pra integradora e **espera a resposta na hora**.
- Mostra o resultado em tempo real: **autorizada** (com chave de acesso, link do XML/PDF)
  ou **rejeitada** (com o motivo do erro).

> **Síncrono** = você clica e espera a resposta imediatamente na tela. A NFC-e funciona
> assim porque é rápida. (A NF-e, na etapa 06, é diferente.)

---

## O fluxo por dentro (o que acontece ao clicar "Emitir")

```
1. Operador cola o JSON da venda  →  sistema valida o formato
2. Sistema busca a empresa + certificado + regras fiscais
3. Sistema monta o payload no formato da integradora
4. Sistema envia para a API da integradora (ambiente de homologação)
5. Integradora responde: autorizada ou rejeitada
6. Sistema salva a nota no banco (com status e resposta)
7. Sistema mostra o resultado na tela
```

### Modelo de dados
```
notas
├── id
├── empresa_id
├── modelo          # 65 (NFC-e) ou 55 (NF-e)
├── status          # rascunho, processando, autorizada, rejeitada, cancelada
├── chave_acesso    # a chave de 44 dígitos (quando autorizada)
├── numero, serie
├── valor_total
├── json_venda      # o JSON original colado
├── payload_enviado
├── resposta_integradora   # o que a integradora devolveu (inclui motivo de erro)
├── xml_url, pdf_url
├── criado_em, atualizado_em
```

---

## Como pedir para a IA

> "No InnoNFe, quero construir a emissão de NFC-e (modelo 65). Uso a integradora
> **[NOME DA ESCOLHIDA]** — segue a documentação da API dela: [COLE OS TRECHOS RELEVANTES].
> Preciso:
> 1. Criar a tabela `notas` com **SQLModel** e gerar a migration com Alembic. [cole os campos acima].
> 2. Uma tela 'Emitir Nota' com: seletor de empresa, uma área para colar o JSON da venda,
>    e uma prévia estruturada (itens, valores, formas de pagamento) que aparece ao colar.
> 3. Definir o formato esperado do JSON de venda (me sugira um formato claro que o
>    InnoSystem poderia gerar) e validar esse JSON ao colar.
> 4. Uma rota de API no servidor que: pega a empresa + certificado + regra fiscal padrão,
>    monta o payload da integradora, envia de forma **síncrona** para o ambiente de
>    **homologação**, e retorna o resultado.
> 5. Exibir o resultado em tempo real: se autorizada, mostrar chave de acesso e links de
>    XML/PDF; se rejeitada, mostrar o motivo de forma clara.
> 6. Salvar tudo na tabela `notas`.
> A comunicação com a integradora e o uso do certificado devem acontecer **no servidor**.
> Comente o código."

---

## Critérios de aceite
- [ ] Consigo colar um JSON de venda e ver a prévia estruturada correta.
- [ ] Ao clicar "Emitir NFC-e", a nota é enviada à integradora (homologação).
- [ ] Uma nota válida volta como **autorizada**, com chave de acesso.
- [ ] Uma nota com erro volta como **rejeitada**, mostrando o motivo.
- [ ] A nota (autorizada ou rejeitada) fica salva na tabela `notas`.

---

## Dicas e armadilhas comuns
- **SEMPRE em homologação primeiro.** Nunca teste em produção — nota fiscal de verdade
  tem efeito legal e fiscal.
- Erros de rejeição da SEFAZ são **normais** durante testes (CSC errado, NCM inválido,
  etc.). Faz parte. É por isso que a etapa 07 tem "reprocessar erro".
- Defina bem o **formato do JSON de venda** logo no começo — ele será a "cola" entre o
  InnoSystem e o InnoNFe. Documente esse formato num arquivo à parte.
- Se a integradora exigir upload do certificado na conta dela (em vez de você enviar a
  cada emissão), ajuste o fluxo conforme a documentação — cada uma funciona um pouco diferente.
- Commit no Git ao terminar. ✅
