# Correção de NFS-e: leitura de XML, conferência fiscal e pedidos de correção

> Parte 2 do [Extrator de Notas Fiscais com IA](../README.md). Todos os dados de exemplo (empresas, CNPJs, alíquotas, PLUs) são fictícios.

Lê os XMLs das notas de serviço, confere cada uma contra a **base de parâmetros fiscais** (código de serviço → PLU e retenções esperadas) e separa o que precisa de **pedido de correção** no SAP. Não há etapa manual no meio: o que a regra consegue decidir vira pedido, e o resto vai para a aba de exceções com o motivo.

```
pasta de XMLs ─┐
fila de NFS-e ─┼─► leitura do XML ─► base de parâmetros ─► regras ─┬─► OK
base fiscal ───┘   (3 layouts)       (código → PLU, %)             ├─► CORRIGIR ─► planilha ─► SAP
                                                                    └─► REVISAR  (exceção + motivo)
```

## O que já funciona

| Etapa | Situação |
|---|---|
| Leitura de XML no **padrão nacional** (obrigatório desde 2026) | pronto |
| Leitura de XML **ABRASF** 1.0 e 2.x | pronto |
| Leitura de XML da **Prefeitura de São Paulo** | pronto |
| Arquivo errado (NF-e de produto, página salva como .xml, XML cortado) explicado em vez de travar | pronto |
| Base de parâmetros fiscais com nomes de coluna configuráveis | pronto (falta testar com a base real) |
| Ligação com a fila de NFS-e por CNPJ + número da nota | pronto (falta testar com a fila real) |
| Regras: IRRF, PIS/COFINS/CSLL, INSS, ISS retido, PLU do pedido | pronto (alíquotas vêm da base) |
| Planilha de saída: Pedidos de correção, Revisar, Conferência | pronto |
| Lançamento no SAP: conexão, laço, log e modo simulação | pronto |
| Lançamento no SAP: **roteiro da transação de correção** | **falta**: vem das macros atuais ou de uma gravação do SAP GUI |

## Como rodar

O processo inteiro roda a partir de **um arquivo**. No dia a dia, basta dar dois cliques em `executar.bat`.

**Uma vez só (configuração):**

1. `pip install -r requirements.txt`
2. Copie `config.exemplo.json` para `config.json` e aponte para os arquivos reais:

```json
"entrada": {
  "pasta_xml": "//servidor/fiscal/xml_nfse",
  "parametros": "C:/Users/voce/Documents/base_parametros_fiscais.xlsx",
  "fila": "C:/Users/voce/Downloads/fila_nfse.xlsx"
},
"saida": { "pasta": "saida", "abrir_planilha": true },
"sap": "simular"
```

Nos caminhos do Windows, use barra normal (`/`) ou barra dupla (`\\`).

**Todo dia:** dois cliques em `executar.bat`, ou `python processar.py`. O programa lê os XMLs, confere com a base, salva a planilha em `saida/` com data e hora, abre essa planilha no Excel e faz a etapa do SAP de acordo com o modo escolhido:

| `"sap"` | O que faz |
|---|---|
| `"nao"` | Só gera a planilha |
| `"simular"` | Gera a planilha e mostra o que seria lançado (padrão) |
| `"lancar"` | Gera a planilha e lança os pedidos de correção (SAP aberto e logado) |

Sem `config.json`, o programa roda com os arquivos de exemplo. Para uma execução pontual diferente, os argumentos sobrescrevem o config, por exemplo `python processar.py --fila outra_fila.xlsx --sap nao`.

Os exemplos usam empresas, CNPJs e alíquotas **fictícios**. As alíquotas de `parametros_fiscais_exemplo.xlsx` são só para teste.

## Status de cada nota

| Status | Quando | O que acontece |
|---|---|---|
| **OK** | Retenções e PLU batem com a base | Nada |
| **CORRIGIR** | Retenção diferente da esperada, ISS retido quando não devia (ou o contrário), PLU do pedido diferente do parâmetro | Vai para a aba *Pedidos de correção* e para o SAP |
| **REVISAR** | Nota cancelada, CNPJ inválido, tomador de outra empresa, código fora da base, código com mais de um PLU, XML ausente ou ilegível | Aba *Revisar*, com o motivo |

Regras usadas no cálculo do esperado:
- base de cálculo das retenções = valor dos serviços
- retenção esperada abaixo de R$ 10,00 é considerada dispensada (configurável)
- diferença de até R$ 0,05 é tratada como arredondamento (configurável)

## Ajustar para as planilhas reais

Copie `config.exemplo.json` para `config.json` e ajuste os nomes das colunas se forem diferentes. A procura ignora maiúsculas, acentos e espaços, e o cabeçalho pode estar em qualquer uma das 10 primeiras linhas. O `processar.py` usa o `config.json` automaticamente.

Também no config:
- `cnpj_raiz_tomador`: os 8 primeiros dígitos do CNPJ da empresa. Nota para outro tomador vai para revisão.
- `tolerancia` e `valor_minimo_retencao`

## O que validar com XMLs reais antes de lançar

1. **PIS/COFINS/CSLL no padrão nacional**: o leitor usa `vRetCSLL` como a soma das três retenções, como está no leiaute vigente. Confira com 2 ou 3 notas reais se o valor bate com o que a área considera retido.
2. **Código municipal de São Paulo**: o XML de SP traz o código da prefeitura (5 dígitos), não o item da LC 116. A base precisa ter a coluna de código municipal para essas notas.
3. Rode alguns dias com `"sap": "simular"` e compare a planilha com o trabalho manual antes de mudar para `"lancar"`.

## Estrutura

```
correcao_nfse/
  leitor_nfse.py   leitura dos 3 layouts de XML -> NotaServico
  nota.py          modelo único da nota
  planilhas.py     base de parâmetros fiscais e fila de NFS-e
  regras.py        OK / CORRIGIR / REVISAR
  processamento.py liga fila, XML, base e regras
  relatorio.py     planilha de saída
  sap.py           SAP GUI Scripting (simulação por padrão)
  utils.py         XML sem namespace (reaproveitado da macro gerar_pedido), CNPJ, números, códigos
processar.py       roda o processo inteiro (lê o config.json)
executar.bat       dois cliques para rodar no Windows
exemplos/          XMLs fictícios dos 3 layouts, base e fila de exemplo
tests/             pytest
```
