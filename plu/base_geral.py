"""Base Geral (aba Base): a única entrada do processo de correção.

Cada linha é uma ocorrência de NFS-e pendente. Daqui saem a ocorrência (para baixar o PDF), o pedido,
o código SAP do fornecedor, o valor e o centro de custo. O filtro separa só o que entra no processo:
time, filas (Status) e valor máximo.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook

from .tributacao import normalizar

COLUNAS = {
    "ocorrencia": ["Ocorrência", "Ocorrencia"],
    "pedido": ["Doc.compras", "Pedido"],
    "fornecedor": ["Fornecedor"],
    "valor": ["Vlr Total", "Valor"],
    "status": ["Status"],
    "centro": ["Cen.", "Centro"],
    "time": ["TIME", "Time"],
}


@dataclass
class Ocorrencia:
    linha: int
    ocorrencia: str
    pedido: str
    fornecedor: str
    valor: Decimal | None
    status: str
    centro: str
    time: str


def texto(v) -> str:
    if v in (None, ""):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _mapear(cabecalho, arquivo: str) -> dict[str, int]:
    nomes = [normalizar(c) for c in cabecalho]
    mapa = {}
    for campo, opcoes in COLUNAS.items():
        for o in opcoes:
            if normalizar(o) in nomes:
                mapa[campo] = nomes.index(normalizar(o))
                break
        else:
            raise ValueError(f"{arquivo}: coluna '{opcoes[0]}' não encontrada na aba da Base Geral")
    return mapa


def ler(caminho: str | Path, aba: str = "Base") -> list[Ocorrencia]:
    wb = load_workbook(caminho, read_only=True, data_only=True)
    if aba not in wb.sheetnames:
        raise ValueError(f"{Path(caminho).name}: aba '{aba}' não encontrada")
    linhas = wb[aba].iter_rows(values_only=True)
    mapa = _mapear(next(linhas), Path(caminho).name)
    saida = []
    for numero, v in enumerate(linhas, start=2):
        oc = texto(v[mapa["ocorrencia"]])
        if not oc:
            continue
        try:
            valor = Decimal(str(v[mapa["valor"]])) if v[mapa["valor"]] not in (None, "") else None
        except InvalidOperation:
            valor = None
        centro = texto(v[mapa["centro"]])
        saida.append(Ocorrencia(
            linha=numero, ocorrencia=oc, pedido=texto(v[mapa["pedido"]]),
            fornecedor=texto(v[mapa["fornecedor"]]), valor=valor, status=texto(v[mapa["status"]]),
            centro=centro.zfill(4) if centro.isdigit() else centro, time=texto(v[mapa["time"]]),
        ))
    wb.close()
    return saida


def filtrar(lista: list[Ocorrencia], filas: list[str], time: str | None,
            valor_maximo: Decimal | None) -> list[Ocorrencia]:
    """Fica com o time pedido, as filas listadas (basta o Status conter o nome) e valor até o máximo."""
    filas_n = [normalizar(f) for f in filas]
    saida = []
    for o in lista:
        if time and normalizar(o.time) != normalizar(time):
            continue
        if filas_n and not any(f in normalizar(o.status) for f in filas_n):
            continue
        if valor_maximo is not None and (o.valor is None or o.valor > valor_maximo):
            continue
        saida.append(o)
    return saida
