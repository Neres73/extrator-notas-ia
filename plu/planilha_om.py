"""Leitura e preenchimento da planilha das OMs (a que a macro VBA usa para lançar na IW32).

A macro VBA lê só as colunas A a F, então:
- a coluna Componente recebe o PLU escolhido
- o status e o motivo vão em duas colunas novas, depois da última coluna usada
O resultado é salvo numa CÓPIA, com o VBA preservado; o arquivo original não é alterado.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from .escolha import Escolha
from .tributacao import normalizar

VERDE = PatternFill("solid", start_color="C6EFCE")
AMARELO = PatternFill("solid", start_color="FFEB9C")

COLUNAS = {
    "om": ["O.M", "OM", "Ordem"],
    "fornecedor": ["Fornecedor", "Cod Fornecedor"],
    "componente": ["Componente", "PLU", "Material"],
    "preco": ["Preço", "Preco", "Valor"],
    "ocorrencia": ["ocorrencia", "Ocorrência"],
}


@dataclass
class LinhaOM:
    linha: int
    om: str
    fornecedor: str
    componente_atual: str | None
    preco: Decimal | None
    ocorrencia: str | None


def _texto(v) -> str | None:
    if v in (None, ""):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _mapear(cabecalho: tuple, arquivo: str) -> dict[str, int]:
    nomes = [normalizar(c) for c in cabecalho]
    mapa = {}
    for campo, opcoes in COLUNAS.items():
        for o in opcoes:
            if normalizar(o) in nomes:
                mapa[campo] = nomes.index(normalizar(o))
                break
        else:
            raise ValueError(f"{arquivo}: coluna '{opcoes[0]}' não encontrada no cabeçalho (linha 1)")
    return mapa


def ler(caminho: str | Path, aba: str | None = None) -> list[LinhaOM]:
    wb = load_workbook(caminho, data_only=True, read_only=True)
    ws = wb[aba] if aba else wb.worksheets[0]
    linhas = ws.iter_rows(values_only=True)
    mapa = _mapear(next(linhas), Path(caminho).name)
    registros = []
    for numero, valores in enumerate(linhas, start=2):
        om = _texto(valores[mapa["om"]])
        if not om:
            continue
        preco = valores[mapa["preco"]]
        try:
            preco = Decimal(str(preco)) if preco not in (None, "") else None
        except InvalidOperation:
            preco = None
        registros.append(LinhaOM(
            linha=numero, om=om, fornecedor=_texto(valores[mapa["fornecedor"]]) or "",
            componente_atual=_texto(valores[mapa["componente"]]), preco=preco,
            ocorrencia=_texto(valores[mapa["ocorrencia"]]),
        ))
    wb.close()
    return registros


def salvar(origem: str | Path, destino: str | Path, resultados: list[tuple[LinhaOM, Escolha]],
           aba: str | None = None, se_revisar: str = "limpar") -> Path:
    origem, destino = Path(origem), Path(destino)
    vba = origem.suffix.lower() == ".xlsm"
    wb = load_workbook(origem, keep_vba=vba)
    ws = wb[aba] if aba else wb.worksheets[0]
    mapa = _mapear(tuple(c.value for c in ws[1]), origem.name)
    col_comp = mapa["componente"] + 1

    ultima = max(i for i, c in enumerate(ws[1], start=1) if c.value not in (None, ""))
    col_status, col_motivo = ultima + 1, ultima + 2
    for col, titulo in ((col_status, "Status PLU"), (col_motivo, "Motivo PLU")):
        cel = ws.cell(row=1, column=col, value=titulo)
        cel.font = Font(bold=True)

    for registro, escolha in resultados:
        cel = ws.cell(row=registro.linha, column=col_comp)
        motivo = escolha.motivo
        if escolha.opcoes:
            motivo += " | Opções: " + " / ".join(escolha.opcoes)
        if escolha.status == "OK":
            if registro.componente_atual and registro.componente_atual != escolha.plu:
                motivo += f" (antes: {registro.componente_atual})"
            cel.value = int(escolha.plu) if escolha.plu.isdigit() else escolha.plu
            cel.fill = VERDE
        else:
            if se_revisar == "limpar":
                cel.value = None
                if registro.componente_atual:
                    motivo += f" (PLU anterior {registro.componente_atual} removido)"
            cel.fill = AMARELO
        ws.cell(row=registro.linha, column=col_status, value=escolha.status)
        ws.cell(row=registro.linha, column=col_motivo, value=motivo)

    ws.column_dimensions[ws.cell(row=1, column=col_motivo).column_letter].width = 90
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino
