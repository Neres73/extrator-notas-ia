"""Leitura da nota direto da tela do NIX NFS-e Cockpit (transação NIXNFSE), sem PDF.

O PDF que o SAP gera é uma imagem; a tela do cockpit já traz o que a escolha do PLU precisa,
vindo do XML da nota:
- "Serviço LC" (ex.: 14.01)
- aba Impostos, coluna "Valores do XML": Valor Total, PIS, COFINS, CSLL, IRRF, INSS

Os campos são achados pelo rótulo na tela (o valor é o primeiro campo à direita do rótulo, na mesma
linha), então não depende do ID de cada campo. Se algo não for achado, a tela inteira é gravada num
arquivo de diagnóstico.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .leitor_pdf import DadosNota
from .tributacao import normalizar

SELECAO = "wnd[0]/usr/ssubSUB_SEL:/MIDAS/NIXNFSE_COCKPIT:0001/"
ARVORE = "wnd[0]/usr/cntlIMAGE_CONTAINER/shellcont/shell/shellcont[0]/shell"
GRID = "wnd[0]/usr/cntlCONT_COCKPIT/shellcont/shell"
TIPOS_TEXTO = {"GuiLabel", "GuiTextField", "GuiCTextField", "GuiTextedit"}

ROTULOS = {
    "servico": "servico lc",
    "valor": "valor total",
    "pis": "pis",
    "cofins": "cofins",
    "csll": "csll",
    "ir": "irrf",
    "inss": "inss",
}


@dataclass
class Elemento:
    id: str
    tipo: str
    texto: str
    x: int
    y: int
    altura: int


def _num(texto: str) -> Decimal | None:
    t = re.sub(r"[^\d,.-]", "", texto or "")
    if not t:
        return None
    try:
        return Decimal(t.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def elementos(no, saida: list[Elemento] | None = None) -> list[Elemento]:
    saida = [] if saida is None else saida
    try:
        tipo = no.Type
        if tipo in TIPOS_TEXTO:
            saida.append(Elemento(no.Id, tipo, str(no.Text or "").strip(), int(no.ScreenLeft),
                                  int(no.ScreenTop), int(no.Height or 1)))
    except Exception:  # noqa: BLE001
        pass
    try:
        filhos = no.Children
        for i in range(filhos.Count):
            elementos(filhos.ElementAt(i), saida)
    except Exception:  # noqa: BLE001
        pass
    return saida


def valores_a_direita(els: list[Elemento], rotulo: str) -> list[str]:
    """Textos dos campos na mesma linha, à direita do rótulo (o 1º é a coluna 'Valores do XML')."""
    alvo = normalizar(rotulo)
    for r in els:
        if normalizar(r.texto).rstrip(":").strip() != alvo:
            continue
        mesma_linha = [e for e in els if e is not r and e.x > r.x and e.texto
                       and abs(e.y - r.y) <= max(r.altura, e.altura) / 2]
        return [e.texto for e in sorted(mesma_linha, key=lambda e: e.x)]
    return []


def ler_campos(els: list[Elemento]) -> dict[str, str | None]:
    campos: dict[str, str | None] = {}
    for campo, rotulo in ROTULOS.items():
        achados = valores_a_direita(els, rotulo)
        if campo == "servico":
            codigo = next((t for t in achados if re.fullmatch(r"\d{1,2}\.\d{2}", t)), None)
            campos["servico"] = codigo
            campos["servico_desc"] = next((t for t in achados if not re.fullmatch(r"[\d.]+", t)), "")
        else:
            campos[campo] = next((t for t in achados if _num(t) is not None), None)
    return campos


def nota_da_tela(ocorrencia: str, campos: dict) -> DadosNota:
    nota = DadosNota(arquivo=f"NIX {ocorrencia}", texto=campos.get("servico_desc") or "")
    servico = campos.get("servico")
    if servico:                                           # o NIX mostra "7.02": a base usa "07.02" (SERV0702)
        grupo, item = servico.split(".")
        servico = f"{int(grupo):02d}.{item}"
    nota.item_lc116 = servico
    nota.origem_codigo = "tela do NIX (XML)"
    nota.valor_servicos = _num(campos.get("valor") or "")
    nota.ir = _num(campos.get("ir") or "")
    nota.inss = _num(campos.get("inss") or "")
    pcc = [_num(campos.get(c) or "") for c in ("pis", "cofins", "csll")]
    if any(v is not None for v in pcc):
        nota.pcc = sum((v or Decimal("0") for v in pcc), Decimal("0"))
    return nota


def _rolar_impostos(s) -> None:
    """Desce a barra de rolagem da aba Impostos (IRRF e INSS ficam abaixo da área visível)."""
    def procurar(no):
        try:
            if no.Type == "GuiScrollContainer":
                yield no
        except Exception:  # noqa: BLE001
            return
        try:
            for i in range(no.Children.Count):
                yield from procurar(no.Children.ElementAt(i))
        except Exception:  # noqa: BLE001
            return
    for sc in procurar(s.findById("wnd[0]/usr")):
        try:
            sc.VerticalScrollbar.Position = sc.VerticalScrollbar.Maximum
        except Exception:  # noqa: BLE001
            pass


def abrir_ocorrencia(s, ocorrencia: str) -> bool:
    s.findById("wnd[0]/tbar[0]/okcd").text = "/nNIXNFSE"
    s.findById("wnd[0]").sendVKey(0)
    s.findById(ARVORE).doubleClickNode("F00003")
    s.findById(SELECAO + "ctxtS_DTINTE-LOW").text = ""
    s.findById(SELECAO + "txtS_OCOR-LOW").text = ocorrencia
    s.findById("wnd[0]/tbar[1]/btn[8]").press()
    try:
        grid = s.findById(GRID)
        if grid.RowCount == 0:
            return False
    except Exception:  # noqa: BLE001
        return False
    grid.currentCellColumn = "OCORRENCIA"
    grid.selectedRows = "0"
    grid.clickCurrentCell()
    try:
        s.findById("wnd[1]").sendVKey(0)
    except Exception:  # noqa: BLE001
        pass
    return True


def ler_ocorrencia(s, ocorrencia: str, pasta_diagnostico: Path | None = None) -> DadosNota | None:
    """None = ocorrência não encontrada no NIX. Campos não achados ficam None (e geram diagnóstico)."""
    if not abrir_ocorrencia(s, ocorrencia):
        return None
    usr = s.findById("wnd[0]/usr")
    els = elementos(usr)
    campos = ler_campos(els)
    if campos.get("ir") is None or campos.get("inss") is None:
        _rolar_impostos(s)
        extra = ler_campos(elementos(s.findById("wnd[0]/usr")))
        campos.update({k: v for k, v in extra.items() if v and not campos.get(k)})
    faltando = [k for k in ROTULOS if not campos.get(k)]
    if faltando and pasta_diagnostico:
        pasta_diagnostico.mkdir(parents=True, exist_ok=True)
        linhas = [f"{e.y:>5} {e.x:>5} {e.tipo:<14} {e.id}  |{e.texto}|" for e in sorted(els, key=lambda e: (e.y, e.x))]
        (pasta_diagnostico / f"nix_{ocorrencia}.txt").write_text(
            f"Campos não achados: {', '.join(faltando)}\n\n" + "\n".join(linhas), encoding="utf-8")
    nota = nota_da_tela(ocorrencia, campos)
    if faltando:
        nota.avisos.append(f"Não achado na tela do NIX: {', '.join(faltando)}")
    return nota
