"""Leitura do PDF da NFS-e (o arquivo que a macro baixar_nota salva).

Tira do texto do PDF só o que a escolha do PLU precisa:
- código de serviço (item da LC 116, ex.: 14.01) -> SERV1401
- valor dos serviços
- retenções federais: IR, PIS/COFINS/CSLL e INSS

Cada prefeitura monta o PDF de um jeito, então a leitura tenta, em ordem:
1. rótulo e valor na mesma linha ("IRRF: R$ 15,00")
2. linha de rótulos seguida de linha de valores (layout em tabela, como o de São Paulo)
3. para o código de serviço: o texto do item da LC 116 que aparece na nota
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .tributacao import Tributacao, normalizar

ZERO = Decimal("0")
VALOR = r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"


@dataclass
class DadosNota:
    arquivo: str
    texto: str
    item_lc116: str | None = None          # "14.01"
    codigo_municipal: str | None = None    # quando a nota só traz o código da prefeitura
    origem_codigo: str = ""                # como o código foi achado (para conferência)
    valor_servicos: Decimal | None = None
    ir: Decimal | None = None
    pcc: Decimal | None = None
    inss: Decimal | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def serv(self) -> str | None:
        return f"SERV{self.item_lc116.replace('.', '')}" if self.item_lc116 else None

    @property
    def leu_retencoes(self) -> bool:
        return any(v is not None for v in (self.ir, self.pcc, self.inss))

    def tributacao(self, base_alternativa: Decimal | None = None) -> Tributacao | None:
        if not self.leu_retencoes:
            return None
        base = self.valor_servicos or base_alternativa or ZERO
        return Tributacao.dos_valores(base, self.ir or ZERO, self.pcc or ZERO, self.inss or ZERO)


def _valor(texto: str) -> Decimal:
    return Decimal(texto.replace(".", "").replace(",", "."))


def extrair_texto(caminho: str | Path) -> str:
    from pypdf import PdfReader

    leitor = PdfReader(str(caminho))
    return "\n".join((p.extract_text() or "") for p in leitor.pages)


# ---------------------------------------------------------------- código de serviço
ROTULOS_CODIGO = [
    r"c[óo]digo\s+de\s+tributa[çc][ãa]o\s+nacional",
    r"item\s+da\s+lista(?:\s+de\s+servi[çc]os?)?",
    r"subitem(?:\s+da\s+lista)?",
    r"c[óo]digo\s+(?:do\s+)?servi[çc]o",
    r"servi[çc]o\s+prestado",
]   # "atividade" fica de fora de propósito: costuma ser o CNAE (ex.: 3314-7/10), não a LC 116


def _normalizar_item(bruto: str) -> str | None:
    d = re.sub(r"\D", "", bruto)
    if re.fullmatch(r"\d{1,2}[.,]\d{2}(?:[.,]\d{2})?", bruto.strip()):
        partes = re.split(r"[.,]", bruto.strip())
        return f"{int(partes[0]):02d}.{partes[1]}"
    if len(d) == 6:                       # código de tributação nacional: 140101
        return f"{d[:2]}.{d[2:4]}"
    if len(d) == 4:                       # 1401
        return f"{d[:2]}.{d[2:]}"
    return None


def achar_codigo(texto: str, descricoes_116: dict[str, str]) -> tuple[str | None, str | None, str]:
    """Devolve (item LC 116, código municipal, como achou)."""
    municipal = None
    for rotulo in ROTULOS_CODIGO:
        for m in re.finditer(rotulo + r"[^\d\n]{0,40}?(\d{1,2}[.,]\d{2}(?:[.,]\d{2})?|\d{4,6})\b", texto, re.I):
            bruto = m.group(1)
            d = re.sub(r"\D", "", bruto)
            if len(d) == 5:               # 5 dígitos = código municipal (ex.: São Paulo)
                municipal = municipal or d
                continue
            item = _normalizar_item(bruto)
            if item and 1 <= int(item[:2]) <= 40:
                return item, municipal, f"rótulo '{m.group(0)[:40].strip()}'"
        m5 = re.search(rotulo + r"[^\d\n]{0,40}?\b(\d{5})\b", texto, re.I)
        if m5:
            municipal = municipal or m5.group(1)

    # reserva: o texto do item da LC 116 aparece na nota (as prefeituras costumam imprimir)
    t = normalizar(texto)
    for serv, descricao in descricoes_116.items():
        trecho = normalizar(descricao)[:60]
        if len(trecho) >= 30 and trecho in t:
            return f"{serv[4:6]}.{serv[6:8]}", municipal, "descrição do item da LC 116 na nota"
    return None, municipal, ""


# ---------------------------------------------------------------- valores
ROTULOS = {
    "valor_servicos": [r"valor\s+(?:total\s+)?d[oa]s?\s+servi[çc]os?", r"valor\s+do\s+servi[çc]o",
                       r"valor\s+total\s+da\s+nota", r"valor\s+bruto"],
    "ir": [r"\birrf\b", r"\bir\b(?!\s*-?\s*isento)", r"imposto\s+de\s+renda"],
    "pis": [r"\bpis(?:/pasep)?\b(?!\s*-\s*d[ée]bito)"],
    "cofins": [r"\bcofins\b(?!\s*-\s*d[ée]bito)"],
    "csll": [r"\bcsll?\b"],
    "pcc": [r"contribui[çc][õo]es\s+sociais\s*-?\s*retidas", r"\bpcc\b", r"\bcsrf\b"],
    "inss": [r"\binss\b", r"contribui[çc][ãa]o\s+previdenci[áa]ria\s*-?\s*retida", r"\bcp\s+retida"],
}


def _inline(texto: str, padroes: list[str]) -> Decimal | None:
    for p in padroes:
        m = re.search(p + r"[^\d\n]{0,30}?" + VALOR, texto, re.I)
        if m:
            return _valor(m.group(1))
    return None


SO_VALORES = re.compile(r"^(?:\s*(?:R\$\s*)?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}\s*)+$")


def _rotulos_da_linha(linha: str) -> list[str]:
    achados = []
    for campo, padroes in ROTULOS.items():
        for p in padroes:
            m = re.search(p, linha, re.I)
            if m:
                achados.append((m.start(), campo))
                break
    return [c for _, c in sorted(achados)]


def _tabela(linhas: list[str]) -> dict[str, Decimal]:
    """Bloco de rótulos seguido de bloco de valores, na mesma quantidade e ordem.

    Cobre os dois jeitos que o texto do PDF sai numa tabela:
      'INSS (R$)  IRRF (R$)  CSLL (R$)'      ou     'INSS (R$)'
      '0,00       15,00      10,00'                 'IRRF (R$)'
                                                    '0,00'
                                                    '15,00'
    """
    achados: dict[str, Decimal] = {}
    i = 0
    while i < len(linhas):
        rotulos: list[str] = []
        j = i
        while j < len(linhas) and not re.search(r"\d,\d{2}", linhas[j]):
            da_linha = _rotulos_da_linha(linhas[j])
            if not da_linha:
                break
            rotulos += da_linha
            j += 1
        if len(rotulos) < 2:
            i = max(j, i + 1)
            continue
        valores: list[str] = []
        k = j
        while k < len(linhas) and SO_VALORES.match(linhas[k]) and len(valores) < len(rotulos):
            valores += re.findall(VALOR, linhas[k])
            k += 1
        if len(valores) == len(rotulos):
            for campo, v in zip(rotulos, valores):
                achados.setdefault(campo, _valor(v))
        i = max(k, i + 1)
    return achados


def ler_nota(caminho: str | Path, descricoes_116: dict[str, str], texto: str | None = None) -> DadosNota:
    caminho = Path(caminho)
    texto = texto if texto is not None else extrair_texto(caminho)
    nota = DadosNota(arquivo=caminho.name, texto=texto)
    if not texto.strip():
        nota.avisos.append("PDF sem texto (imagem escaneada)")
        return nota

    nota.item_lc116, nota.codigo_municipal, nota.origem_codigo = achar_codigo(texto, descricoes_116)

    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    tabela = _tabela(linhas)

    def campo(nome: str) -> Decimal | None:
        if nome in tabela:
            return tabela[nome]
        return _inline(texto, ROTULOS[nome])

    nota.valor_servicos = campo("valor_servicos")
    nota.ir = campo("ir")
    nota.inss = campo("inss")
    pcc_total = campo("pcc")
    pis, cofins, csll = campo("pis"), campo("cofins"), campo("csll")
    if pcc_total is not None:
        nota.pcc = pcc_total
    elif any(v is not None for v in (pis, cofins, csll)):
        nota.pcc = (pis or ZERO) + (cofins or ZERO) + (csll or ZERO)
    return nota
