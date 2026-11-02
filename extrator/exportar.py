"""Gera a planilha de saída: uma aba com as notas e outra com os itens."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .modelos import ResultadoExtracao

AMARELO = PatternFill("solid", start_color="FFF2CC")
NEGRITO = Font(bold=True)


def salvar_excel(resultados: list[ResultadoExtracao], destino: str | Path) -> Path:
    destino = Path(destino)
    planilha = Workbook()

    notas = planilha.active
    notas.title = "Notas"
    notas.append([
        "Arquivo", "Status", "Fornecedor", "CNPJ", "Nº Nota", "Emissão",
        "Vencimento", "Valor Total", "Provedor", "Motivos para revisar",
    ])
    for r in resultados:
        n = r.nota
        notas.append([
            r.arquivo, r.status, n.fornecedor, n.cnpj_fornecedor, n.numero_nota,
            n.data_emissao, n.data_vencimento,
            float(n.valor_total) if n.valor_total is not None else None,
            r.provedor, "; ".join(r.motivos),
        ])
        if r.status != "OK":
            for celula in notas[notas.max_row]:
                celula.fill = AMARELO

    itens = planilha.create_sheet("Itens")
    itens.append(["Arquivo", "Nº Nota", "Descrição", "Quantidade", "Valor Total"])
    for r in resultados:
        for i in r.nota.itens:
            itens.append([r.arquivo, r.nota.numero_nota, i.descricao, float(i.quantidade), float(i.valor_total)])

    for aba, formatos in ((notas, {"F": "DD/MM/YYYY", "G": "DD/MM/YYYY", "H": "R$ #,##0.00"}),
                          (itens, {"E": "R$ #,##0.00"})):
        for celula in aba[1]:
            celula.font = NEGRITO
        aba.freeze_panes = "A2"
        for coluna, formato in formatos.items():
            for celula in aba[coluna][1:]:
                celula.number_format = formato
        for indice, coluna in enumerate(aba.columns, start=1):
            largura = max(len(str(c.value)) if c.value is not None else 0 for c in coluna)
            aba.column_dimensions[get_column_letter(indice)].width = min(max(largura + 2, 10), 60)

    destino.parent.mkdir(parents=True, exist_ok=True)
    planilha.save(destino)
    return destino
