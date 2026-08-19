# Orçamento — Nota de Devolução (NF-e mod. 55)

**Escopo:** Implementar emissão de NF-e de devolução no InnoFiscal, com formulário guiado por seções. Upload do XML da nota original é opcional — se subir, o formulário vem pré-preenchido; se não, todos os campos ficam abertos pra digitar manualmente.

**Valor:** **R$ 1.000,00** (pagamento à vista na entrega)
**Prazo:** 5 dias úteis após aprovação
**Ambiente de entrega:** `https://inno-fiscal.fly.dev`

---

## 1. O que entra

- Nova tela **Emitir Devolução** no InnoFiscal (menu lateral).
- Upload **opcional** de XML da NF-e original (`.xml` autorizado) ou busca por chave de acesso.
- Parser do XML que preenche automaticamente: emitente original, destinatário, itens, valores, chave de referência.
- **Preenchimento manual** de todos os campos quando o XML não estiver disponível.
- Formulário dividido em **5 seções** editáveis antes da transmissão.
- Regras fiscais: CFOP de devolução (1202/1411/1662/2202/2411/2662 conforme origem), `finNFe=4` (devolução), `refNFe` apontando pra chave original, tributos espelhados da nota de origem.
- Transmissão SEFAZ via ACBr API, retorno de status, XML autorizado e DANFE.
- Cancelamento da devolução (mesmo fluxo de cancelamento já existente).

---

## 2. Upload do XML (opcional) e pré-preenchimento

### 2.1. Tela

![Upload XML devolução](img/01-devolucao-upload.png)

Três formas de começar a devolução:

- **Subir XML da nota original** — arquivo `.xml` autorizado, até 2 MB.
- **Chave de acesso (44 dígitos)** — busca o XML já emitido no próprio InnoFiscal.
- **Preencher manualmente** — pula o upload e abre o formulário em branco.

### 2.2. O que é extraído do XML (quando enviado)

| Campo do XML                          | Preenche no formulário           |
|---------------------------------------|----------------------------------|
| `emit/CNPJ`, `emit/xNome`             | Destinatário da devolução        |
| `dest/CNPJ` ou `dest/CPF`, `dest/xNome` | Emitente da devolução (loja)   |
| `dest/enderDest/*`                    | Endereço do destinatário         |
| `det/prod` (todos os itens)           | Lista de itens da devolução      |
| `det/imposto/*`                       | Tributos espelhados por item     |
| `total/ICMSTot/vNF`                   | Valor total da devolução         |
| `chNFe` (44 dígitos)                  | `refNFe` (nota referenciada)     |
| `ide/natOp`                           | Base pra sugerir CFOP inverso    |

### 2.3. O que o parser NÃO adivinha (usuário confirma)

- CFOP final (sugere, mas usuário aprova).
- Motivo da devolução (texto livre em `infAdic/infCpl`).
- Se é devolução total ou parcial.

---

## 3. Seções do formulário

Todos os campos abaixo são editáveis independentemente de o XML ter sido enviado ou não. Sem XML, o usuário digita direto; com XML, os campos já vêm preenchidos e podem ser ajustados.

### 3.1. Seção — Nota de origem

- Chave de acesso (44 dígitos) — **obrigatório**.
- Número / série / data de emissão da original.
- Motivo da devolução — texto livre, mín. 15 caracteres.

### 3.2. Seção — Emitente (loja)

Pré-preenchido pela empresa logada no InnoFiscal. Só leitura:
- CNPJ, IE, razão social, endereço.

### 3.3. Seção — Destinatário (cliente original ou fornecedor)

- CPF/CNPJ, nome/razão social.
- Endereço completo.
- Inscrição estadual (ou ISENTO).

### 3.4. Seção — Itens

Tabela de itens. Sem XML, o usuário adiciona linhas manualmente. Com XML, vem preenchida.

| Campo          | Origem       | Editável? |
|----------------|--------------|-----------|
| Código         | XML `cProd`  | Sim       |
| Descrição      | XML `xProd`  | Sim       |
| NCM            | XML `NCM`    | Sim       |
| CFOP           | Sugerido     | **Sim**   |
| Quantidade     | XML `qCom`   | Sim (≤ original) |
| Valor unitário | XML `vUnCom` | Sim       |
| CST/CSOSN      | XML          | Sim       |
| Tributos       | XML          | Sim       |

Botões **Adicionar item** e **Remover item**.

### 3.5. Seção — Totais e transmissão

- Valor total (calculado).
- Natureza da operação: `Devolucao de venda` (padrão, editável).
- Finalidade: `4 - Devolução` (fixo).
- Botão **Transmitir SEFAZ**.

---

## 4. Pagamento

- **R$ 1.000,00**
