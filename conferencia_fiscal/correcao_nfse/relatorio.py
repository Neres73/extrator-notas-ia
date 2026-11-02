"""Planilha de saída.

Abas:
- Pedidos de correção: só as notas CORRIGIR. É a entrada da etapa de lançamento no SAP.
- Revisar:             exceções, com o motivo (inclui arquivos XML que não puderam ser lidos).
- Conferência:         todas as notas, com o que foi lido do XML, o esperado e o status.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .processamento import Lote
from .regras import Resultado

CORES = {"OK": "E2EFDA", "CORRIGIR": "FCE4D6", "REVISAR": "FFF2CC"}
MOEDA = 'R$ #,##0.00'

COLUNAS_PEDIDO = [
    "Ocorrência", "Pedido", "Nº Nota", "CNPJ Prestador", "Prestador", "Emissão", "Código Serviço",
    "PLU correto", "PLU atual", "Valor Serviços", "IRRF esperado", "IRRF nota", "PCC esperado", "PCC nota",
    "INSS esperado", "INSS nota", "ISS retido", "Divergências", "Arquivo XML",
]
COLUNAS_CONFERENCIA = [
    "Status", "Ocorrência", "Pedido", "Nº Nota", "Layout", "CNPJ Prestador", "Prestador", "CNPJ Tomador",
    "Emissão", "Competência", "Item LC 116", "Cód. Tributação Nacional", "Cód. Municipal", "Descrição do serviço",
    "Valor Serviços", "Base Cálculo", "Alíquota ISS %", "Valor ISS", "ISS retido", "IRRF retido", "PCC retido",
    "INSS retido", "Valor Líquido", "PLU correto", "Motivos", "Avisos da leitura", "Arquivo XML",
]
MONETARIAS = {"Valor Serviços", "IRRF esperado", "IRRF nota", "PCC esperado", "PCC nota", "INSS esperado",
              "INSS nota", "Base Cálculo", "Valor ISS", "IRRF retido", "PCC retido", "INSS retido", "Valor Líquido"}


def _f(v):
    return float(v) if v is not None else None


def _linha_pedido(r: Resultado) -> list:
    n, f = r.nota, r.fila
    return [
        f.ocorrencia if f else None, f.pedido if f else None, n.numero, n.cnpj_prestador, n.nome_prestador,
        n.data_emissao, n.item_lc116 or n.codigo_municipal, r.plu_correto, f.plu_atual if f else None,
        _f(n.valor_servicos), _f(r.esperado.get("IRRF")), _f(n.irrf_retido),
        _f(r.esperado.get("PIS/COFINS/CSLL")), _f(n.pcc_retido), _f(r.esperado.get("INSS")), _f(n.inss_retido),
        "Sim" if n.iss_retido else "Não", "; ".join(r.motivos), n.arquivo,
    ]


def _linha_conferencia(r: Resultado) -> list:
    n, f = r.nota, r.fila
    if n is None:
        return [r.status, f.ocorrencia if f else None, f.pedido if f else None, f.numero_nota if f else None,
                None, f.cnpj_prestador if f else None] + [None] * 18 + ["; ".join(r.motivos), None, None]
    return [
        r.status, f.ocorrencia if f else None, f.pedido if f else None, n.numero, n.layout, n.cnpj_prestador,
        n.nome_prestador, n.cnpj_tomador, n.data_emissao, n.competencia, n.item_lc116,
        n.codigo_tributacao_nacional, n.codigo_municipal, n.descricao_servico, _f(n.valor_servicos),
        _f(n.base_calculo), _f(n.aliquota_iss), _f(n.valor_iss), "Sim" if n.iss_retido else "Não",
        _f(n.irrf_retido), _f(n.pcc_retido), _f(n.inss_retido), _f(n.valor_liquido), r.plu_correto,
        "; ".join(r.motivos), "; ".join(n.avisos), n.arquivo,
    ]


def _formatar(aba, colunas: list[str], status_col: int | None = None) -> None:
    for c in aba[1]:
        c.font = Font(bold=True)
    aba.freeze_panes = "A2"
    for i, nome in enumerate(colunas, start=1):
        letra = get_column_letter(i)
        if nome in MONETARIAS:
            for c in aba[letra][1:]:
                c.number_format = MOEDA
        elif nome in ("Emissão", "Competência"):
            for c in aba[letra][1:]:
                c.number_format = "DD/MM/YYYY"
        largura = max((len(str(c.value)) for c in aba[letra] if c.value is not None), default=8)
        aba.column_dimensions[letra].width = min(max(largura + 2, 10), 60)
    if status_col is not None:
        for linha in aba.iter_rows(min_row=2):
            cor = CORES.get(linha[status_col].value)
            if cor:
                for c in linha:
                    c.fill = PatternFill("solid", start_color=cor)
    aba.auto_filter.ref = aba.dimensions


def salvar(lote: Lote, destino: str | Path) -> Path:
    destino = Path(destino)
    wb = Workbook()

    pedidos = wb.active
    pedidos.title = "Pedidos de correção"
    pedidos.append(COLUNAS_PEDIDO)
    for r in lote.resultados:
        if r.status == "CORRIGIR":
            pedidos.append(_linha_pedido(r))
    _formatar(pedidos, COLUNAS_PEDIDO)

    revisar = wb.create_sheet("Revisar")
    colunas_rev = ["Ocorrência", "Pedido", "Nº Nota", "CNPJ Prestador", "Prestador", "Motivo", "Arquivo XML"]
    revisar.append(colunas_rev)
    for r in lote.resultados:
        if r.status == "REVISAR":
            n, f = r.nota, r.fila
            revisar.append([f.ocorrencia if f else None, f.pedido if f else None,
                            n.numero if n else (f.numero_nota if f else None),
                            n.cnpj_prestador if n else (f.cnpj_prestador if f else None),
                            n.nome_prestador if n else None, "; ".join(r.motivos), n.arquivo if n else None])
    for arquivo, motivo in lote.arquivos_invalidos:
        revisar.append([None, None, None, None, None, f"XML não lido: {motivo}", arquivo])
    _formatar(revisar, colunas_rev)

    conf = wb.create_sheet("Conferência")
    conf.append(COLUNAS_CONFERENCIA)
    for r in lote.resultados:
        conf.append(_linha_conferencia(r))
    _formatar(conf, COLUNAS_CONFERENCIA, status_col=0)

    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino
