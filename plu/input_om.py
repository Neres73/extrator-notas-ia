"""Planilha de criação de OMs em massa (a que é carregada na transação de criação, ex.: ZTPM0032).

O modelo tem duas abas que importam:
- 'Criar OM Massa': onde as linhas são preenchidas (é o que a equipe preenche à mão)
- 'Input': puxa a 'Criar OM Massa' por fórmula; é a aba que a transação lê

Por isso o preenchimento é feito pelo próprio Excel (COM): as fórmulas da 'Input' são recalculadas e
o arquivo fica igual ao que a equipe gera à mão. O modelo nunca é alterado: cada lote é uma cópia.
O Local de instalação sai da aba 'Base Locais' do próprio modelo e é gravado como valor.
"""

from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from .tributacao import normalizar

ABA_DADOS = "Criar OM Massa"
ABA_INPUT = "Input"
ABA_LOCAIS = "Base Locais"


def chave(nome) -> str:
    """'Grupo de codes – codificação' e 'Grupo de codes - codificação' viram a mesma chave."""
    return re.sub(r"[^a-z0-9]", "", normalizar(nome))


def ler_modelo(modelo: str | Path) -> tuple[dict[str, str], int]:
    """Devolve {centro de custo: local de instalação} e quantas linhas a aba Input comporta."""
    wb = load_workbook(modelo, read_only=True)
    locais = {}
    for cc, _, local, *_ in wb[ABA_LOCAIS].iter_rows(min_row=2, values_only=True):
        if cc not in (None, "") and local:
            cc = str(int(cc) if isinstance(cc, float) else cc).strip()
            locais[cc.zfill(4) if cc.isdigit() else cc] = str(local).strip()
    capacidade = sum(1 for (a,) in wb[ABA_INPUT].iter_rows(min_row=2, max_col=1, values_only=True)
                     if isinstance(a, str) and a.startswith("="))
    wb.close()
    return locais, capacidade


def ler_regioes(caminho: str | Path, aba: str = "Regiões") -> dict[str, tuple[str, str]]:
    """Planilha de regiões (.xlsb ou .xlsx): {centro de custo: (local de instalação, último status da loja)}."""
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".xlsb":
        from pyxlsb import open_workbook
        with open_workbook(str(caminho)) as wb, wb.get_sheet(aba) as sh:
            linhas = [[c.v for c in r] for r in sh.rows()]
    else:
        wb = load_workbook(caminho, read_only=True, data_only=True)
        linhas = [list(r) for r in wb[aba].iter_rows(values_only=True)]
        wb.close()
    cab = [chave(c) for c in linhas[0]]
    i_cc, i_local = cab.index(chave("CC Texto")), cab.index(chave("Local de instalação"))
    i_status = cab.index(chave("Ultimo Status da Loja")) if chave("Ultimo Status da Loja") in cab else None
    saida = {}
    for v in linhas[1:]:
        if len(v) <= i_local or not v[i_cc] or not v[i_local]:
            continue
        cc = str(int(v[i_cc]) if isinstance(v[i_cc], float) else v[i_cc]).strip()
        status = str(v[i_status] or "").strip() if i_status is not None and len(v) > i_status else ""
        saida[cc.zfill(4) if cc.isdigit() else cc] = (str(v[i_local]).strip(), status)
    return saida


def montar_linha(texto_breve: str, centro: str, local: str, fixos: dict, hoje: date | None = None) -> dict:
    """Uma linha da 'Criar OM Massa', por nome de coluna. Os campos fixos vêm do config."""
    linha = dict(fixos)
    linha.update({
        "Texto breve": texto_breve,
        "Centro de custo": centro,
        "Local de instalação": local,
        "Data base início": (hoje or date.today()).strftime("%d.%m.%Y"),
    })
    return linha


def preencher(modelo: str | Path, destino: str | Path, linhas: list[dict]) -> Path:
    import win32com.client as win32  # só existe no Windows

    destino = Path(destino).resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(modelo, destino)

    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AskToUpdateLinks = False
    wb = xl.Workbooks.Open(str(destino), UpdateLinks=0)
    try:
        ws = wb.Worksheets(ABA_DADOS)
        ultima_col = ws.Cells(1, ws.Columns.Count).End(-4159).Column        # xlToLeft
        colunas = {chave(ws.Cells(1, c).Value): c for c in range(1, ultima_col + 1) if ws.Cells(1, c).Value}
        faltando = [n for n in linhas[0] if chave(n) not in colunas] if linhas else []
        if faltando:
            raise ValueError(f"Colunas não encontradas na aba '{ABA_DADOS}' do modelo: {', '.join(faltando)}")

        ultima_linha = max(ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1, 2)
        ws.Range(ws.Cells(2, 1), ws.Cells(ultima_linha, ultima_col)).ClearContents()
        for i, linha in enumerate(linhas, start=2):
            for nome, valor in linha.items():
                if valor in (None, ""):
                    continue
                cel = ws.Cells(i, colunas[chave(nome)])
                if isinstance(valor, str):
                    cel.NumberFormat = "@"                                    # mantém zeros à esquerda
                cel.Value = valor
        xl.CalculateFull()
        wb.Save()
    finally:
        wb.Close(SaveChanges=False)
        xl.Quit()
    return destino
