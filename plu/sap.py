"""Passos no SAP GUI (Scripting), a partir das gravações da equipe.

- ordens_dos_pedidos: ME2K com vários pedidos de uma vez -> ordem (AUFNR) e centro de custo de cada um
- criar_oms: transação de criação em massa com o caminho da planilha -> relatório
  "Relatório dos Registros" (Registro, Num. Ordem, Num. Nota, Descrição)
- preencher_componente: IW32, igual à macro da planilha "teste om" (fornecedor, PLU, preço, requisitante)

O SAP precisa estar aberto e logado. Nada aqui é chamado sem o SAP (os testes usam objetos falsos).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from .tributacao import normalizar

GRID_ME2K = "wnd[0]/usr/cntlGRID1/shellcont/shell/shellcont[1]/shell/shellcont[1]/shell"

_IW32 = "wnd[0]/usr/subSUB_ALL:SAPLCOIH:3001/ssubSUB_LEVEL:SAPLCOIH:"
PARCEIRO = (_IW32 + "1100/tabsTS_1100/tabpIHKZ/ssubSUB_AUFTRAG:SAPLCOIH:1120/subHEADER:SAPLCOIH:0154/"
            "subPARTNER:SAPLIPAR:0421/ctxtDIIHPA-I_PARNR")
ABA_COMPONENTES = _IW32 + "1100/tabsTS_1100/tabpMUEB"
MATERIAL = (_IW32 + "1107/tabsTS_1100/tabpMUEB/ssubSUB_AUFTRAG:SAPLCOMK:3020/"
            "tblSAPLCOMKTCTRL_3020/ctxtRESBD-MATNR[1,0]")
DETALHE = "wnd[1]/usr/subMAT_DETAIL_EXTERN:SAPLCOMD:3170/"


@dataclass
class Registro:
    registro: int
    ordem: str
    nota: str
    descricao: str

    @property
    def ok(self) -> bool:
        return bool(self.ordem) and "sucesso" in normalizar(self.descricao)


def sessao():
    import win32com.client  # só existe no Windows

    try:
        sap = win32com.client.GetObject("SAPGUI").GetScriptingEngine
        return sap.Children(0).Children(0)
    except Exception as erro:  # noqa: BLE001
        raise RuntimeError("SAP não encontrado: abra o SAP GUI, faça login e deixe uma sessão aberta") from erro


def _transacao(s, codigo: str) -> None:
    s.findById("wnd[0]/tbar[0]/okcd").text = f"/n{codigo}"
    s.findById("wnd[0]").sendVKey(0)


def _existe(s, ident: str) -> bool:
    try:
        s.findById(ident)
        return True
    except Exception:  # noqa: BLE001
        return False


def _barra(s) -> tuple[str, str]:
    barra = s.findById("wnd[0]/sbar")
    return barra.MessageType, barra.Text


# ------------------------------------------------------------------ leitura de relatórios
def _achar_grid(no):
    try:
        if no.Type == "GuiShell" and no.SubType == "GridView":
            return no
    except Exception:  # noqa: BLE001
        pass
    try:
        filhos = no.Children
    except Exception:  # noqa: BLE001
        return None
    for i in range(filhos.Count):
        achado = _achar_grid(filhos.ElementAt(i))
        if achado is not None:
            return achado
    return None


def ler_grid(grid) -> list[dict[str, str]]:
    """Linhas de um ALV grid, com as colunas pelo título exibido normalizado (e pelo nome técnico)."""
    nomes = [grid.ColumnOrder.ElementAt(i) for i in range(grid.ColumnOrder.Count)]
    titulos = {n: normalizar(grid.GetDisplayedColumnTitle(n)) for n in nomes}
    passo = max(int(grid.VisibleRowCount or 1), 1)
    linhas = []
    for i in range(grid.RowCount):
        if i % passo == 0:
            grid.firstVisibleRow = i                       # o grid só entrega o que já foi carregado
        linha = {}
        for n in nomes:
            valor = str(grid.GetCellValue(i, n)).strip()
            linha[n] = valor
            linha[titulos[n]] = valor
        linhas.append(linha)
    return linhas


def ler_lista(usr) -> list[dict[str, str]]:
    """Lista ALV clássica (rótulos lbl[coluna,linha]): acha o cabeçalho e lê as linhas abaixo dele."""
    celulas: dict[int, list[tuple[int, str]]] = {}
    for i in range(usr.Children.Count):
        c = usr.Children.ElementAt(i)
        m = re.search(r"\[(\d+),(\d+)\]$", c.Id)
        if m and c.Text.strip():
            celulas.setdefault(int(m[2]), []).append((int(m[1]), c.Text.strip()))
    cabecalho = next((y for y in sorted(celulas) if any(normalizar(t) == "num. ordem" for _, t in celulas[y])), None)
    if cabecalho is None:
        return []
    colunas = sorted((x, normalizar(t)) for x, t in celulas[cabecalho])
    linhas = []
    for y in sorted(k for k in celulas if k > cabecalho):
        linha = {}
        for x, t in celulas[y]:
            titulo = next((nome for cx, nome in reversed(colunas) if cx <= x + 1), colunas[0][1])
            linha[titulo] = (linha.get(titulo, "") + " " + t).strip()
        linhas.append(linha)
    return linhas


def registros_do_relatorio(linhas: list[dict[str, str]]) -> list[Registro]:
    saida = []
    for ln in linhas:
        reg = re.sub(r"\D", "", ln.get("registro", ""))
        if not reg:
            continue
        saida.append(Registro(int(reg), re.sub(r"\D", "", ln.get("num. ordem", "")),
                              re.sub(r"\D", "", ln.get("num. nota", "")), ln.get("descricao", "")))
    return saida


# ------------------------------------------------------------------ ME2K
def ordens_dos_pedidos(s, pedidos: list[str]) -> dict[str, list[tuple[str, str]]]:
    """{pedido: [(ordem, centro de custo), ...]} sem repetição. Pedido sem ordem fica de fora."""
    import win32clipboard

    _transacao(s, "ME2K")
    s.findById("wnd[0]/usr/ctxtEK_KOSTL-LOW").text = "*"
    # "Abrangência da lista" (LISTU) fica com o valor padrão: vazio dá erro na ME2K
    s.findById("wnd[0]/usr/btn%_S_EBELN_%_APP_%-VALU_PUSH").press()
    s.findById("wnd[1]/tbar[0]/btn[16]").press()               # limpa a seleção anterior
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText("\r\n".join(pedidos))
    win32clipboard.CloseClipboard()
    s.findById("wnd[1]/tbar[0]/btn[24]").press()               # colar da área de transferência
    s.findById("wnd[1]/tbar[0]/btn[8]").press()
    s.findById("wnd[0]/tbar[1]/btn[8]").press()

    grid = _achar_grid(s.findById("wnd[0]/usr")) if not _existe(s, GRID_ME2K) else s.findById(GRID_ME2K)
    if grid is None:
        tipo, texto = _barra(s)
        if tipo in ("S", "W", "I") and texto:                  # ex.: "Nenhum dado selecionado"
            return {}
        raise RuntimeError(f"ME2K não mostrou a lista de pedidos: {texto or 'sem mensagem'}")
    resultado: dict[str, list[tuple[str, str]]] = {}
    for ln in ler_grid(grid):
        pedido, ordem = ln.get("EBELN", ""), ln.get("AUFNR", "").lstrip("0")
        if pedido and ordem:
            par = (ordem, ln.get("KOSTL", "").lstrip("0"))
            resultado.setdefault(pedido, [])
            if par not in resultado[pedido]:
                resultado[pedido].append(par)
    return resultado


# ------------------------------------------------------------------ criação em massa
def criar_oms(s, transacao: str, caminho: str) -> list[Registro]:
    _transacao(s, transacao)
    campo = s.findById("wnd[0]/usr/ctxtP_ARQL")
    if len(caminho) > campo.MaxLength:
        raise RuntimeError(f"Caminho da planilha com {len(caminho)} caracteres; o campo da {transacao} aceita "
                           f"{campo.MaxLength}. Use uma pasta_saida mais curta no config")
    campo.text = caminho
    s.findById("wnd[0]/tbar[1]/btn[8]").press()
    if _existe(s, "wnd[1]"):
        raise RuntimeError(f"{transacao} abriu uma janela inesperada: {s.findById('wnd[1]').Text}")
    usr = s.findById("wnd[0]/usr")
    grid = _achar_grid(usr)
    linhas = ler_grid(grid) if grid is not None else ler_lista(usr)
    registros = registros_do_relatorio(linhas)
    if not registros:
        raise RuntimeError(f"{transacao} não mostrou o Relatório dos Registros: {_barra(s)[1] or 'sem mensagem'}")
    return registros


# ------------------------------------------------------------------ IW32
def preencher_componente(s, ordem: str, fornecedor: str, plu: str, valor: Decimal, requisitante: str,
                         grupo_compras: str, org_compras: str) -> str:
    """Mesmos passos da macro 'componente' da planilha teste om. Devolve a mensagem da barra do SAP."""
    _transacao(s, "IW32")
    s.findById("wnd[0]/usr/ctxtCAUFVD-AUFNR").text = ordem
    s.findById("wnd[0]").sendVKey(0)
    s.findById(PARCEIRO).text = fornecedor
    s.findById(ABA_COMPONENTES).select()
    s.findById(MATERIAL).text = plu
    s.findById("wnd[0]").sendVKey(0)
    s.findById("wnd[1]").sendVKey(0)
    s.findById("wnd[2]").sendVKey(0)
    s.findById(DETALHE + "txtRESBD-MENGE").text = "1"
    s.findById(DETALHE + "txtRESBD-GPREIS").text = f"{valor:.2f}".replace(".", ",")
    s.findById(DETALHE + "ctxtRESBD-EKGRP").text = grupo_compras
    s.findById(DETALHE + "ctxtRESBD-EKORG").text = org_compras
    s.findById(DETALHE + "ctxtRESBD-LIFNR").text = fornecedor
    s.findById(DETALHE + "txtRESBD-AFNAM").text = requisitante
    s.findById("wnd[1]/tbar[0]/btn[0]").press()
    s.findById("wnd[0]/tbar[1]/btn[25]").press()
    s.findById("wnd[0]/tbar[0]/btn[11]").press()
    s.findById("wnd[1]/usr/btnSPOP-OPTION1").press()
    tipo, texto = _barra(s)
    if tipo in ("E", "A"):
        raise RuntimeError(texto)
    return texto
