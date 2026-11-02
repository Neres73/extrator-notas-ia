# Escolher PLU das OMs pela NFS-e

> Parte 3 do [Extrator de Notas Fiscais com IA](../README.md). Os testes usam só dados fictícios; a base fiscal e as planilhas reais não fazem parte do repositório.

Preenche a coluna **Componente** (PLU) da planilha das OMs lendo a NFS-e de cada ocorrência e cruzando com a **base de parâmetros fiscais**. Depois é só rodar a macro VBA de sempre, que lança na IW32.

```
planilha das OMs ──► PDF da nota (pela ocorrência) ──► código de serviço + retenções federais
                                                              │
base fiscal: categorias liberadas do fornecedor + aba PLUs ◄──┘
                                                              │
                 Componente preenchido (verde) ou linha para revisar (amarelo, com o motivo)
```

## A regra (a mesma da legenda da base fiscal)

1. **Código de serviço da NFS-e** → SERV (14.01 → `SERV1401`)
2. **Tributação federal da nota** (IR, PCC, INSS) → qual categoria liberada para o fornecedor vale. Ex.: nota sem retenção → *Manutenção corretiva*; nota com PCC → *Preventiva sem cessão*; PCC + INSS 11% → *Preventiva com cessão*
3. **SERV + categoria** → PLU (aba PLUs). Se houver mais de um PLU, decide a conta contábil preferida ou o PLU fixado no config

Se a tributação da nota não bate com nenhum padrão liberado para o fornecedor, a linha fica em amarelo com o aviso **"vai dar crítica no agendamento"**. É o erro que hoje só aparece depois.

## Uso

**Uma vez:** `pip install -r requirements.txt`, copie `config.exemplo.json` para `config.json` e ajuste.

**Todo dia:** dois cliques em `executar.bat`. Sai uma **cópia** da planilha em `saida/` com:
- **Componente** preenchido (verde) ou vazio (amarelo)
- colunas **Status PLU** e **Motivo PLU** no fim da planilha (a macro VBA só lê as colunas A a F)
- a macro VBA preservada; a planilha original não é alterada

Antes de rodar a macro da IW32, resolva as linhas em amarelo. Como a macro percorre todas as linhas, uma linha sem PLU para no SAP.

## config.json

| Campo | Para que serve |
|---|---|
| `planilha_om` | A planilha das OMs (.xlsm) |
| `base_fiscal` | A "Relação prestadores e parâmetro fiscal" (.xlsb ou .xlsx) |
| `pasta_pdfs` | Onde ficam os PDFs das notas. O arquivo é achado pela ocorrência no nome (`123456789.pdf`) |
| `baixar_notas.usar` + `pasta_macro_baixar_nota` | Liga o download dos PDFs que faltam pela macro **baixar_nota** (SAP, NIXNFSE). Os PDFs saem com o nome da ocorrência |
| `contas_preferidas` | Quando a categoria tem mais de um PLU, a ordem das contas contábeis a usar. Ex.: `["400200"]` |
| `plu_preferido` | PLU fixo para um SERV + categoria. Ex.: `{"SERV1401\|100": "9009999"}` |
| `codigos_municipais` | De-para do código da prefeitura (São Paulo usa 5 dígitos) para o item da LC 116. Ex.: `{"07498": "14.01"}` |
| `se_revisar` | `"limpar"` (padrão) apaga o PLU antigo das linhas em amarelo; `"manter"` deixa como estava |

Nos caminhos do Windows, use `/` ou `\\`.

## Leitura do PDF

Cada prefeitura monta o PDF de um jeito. A leitura procura:
- **código de serviço**: rótulos como "Código de Tributação Nacional", "Item da Lista", "Código do Serviço". Se não achar, procura o **texto do item da LC 116** que a nota imprime. O CNAE ("Atividade") é ignorado de propósito
- **retenções**: rótulo e valor na mesma linha, ou tabela de rótulos seguida da linha de valores (como no layout de São Paulo e no DANFSe nacional)

Os layouts dos testes são simulados. **Calibre com PDFs reais** antes de usar em produção: rode com algumas notas e confira a coluna Motivo PLU.

## Testes

```bash
python -m pytest
```

Os testes usam só dados fictícios (base, planilha e PDFs gerados na hora; os PDFs precisam do `reportlab`).
