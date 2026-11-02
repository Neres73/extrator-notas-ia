"""Base de parâmetros fiscais (Relação prestadores e parâmetro fiscal).

Abas usadas:
- 'Prestadores x REINF': Cod SAP do fornecedor -> categorias de serviço liberadas e a tributação de cada uma
- 'PLUs': PLU -> SERV (código de serviço da NFS-e), categoria e conta contábil

Aceita .xlsb (como a base vem hoje) e .xlsx.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .tributacao import Tributacao, normalizar


@dataclass(frozen=True)
class CategoriaPrestador:
    categoria: int
    descricao: str
    padrao: str
    impostos: str

    @property
    def tributacao(self) -> Tributacao:
        return Tributacao.do_texto(self.impostos)


@dataclass(frozen=True)
class Plu:
    plu: str
    descricao: str
    serv: str              # ex.: SERV1401
    descricao_116: str     # texto do item da LC 116
    categoria: int
    descricao_categoria: str
    conta: str
    descricao_conta: str


@dataclass
class BaseFiscal:
    prestadores: dict[str, list[CategoriaPrestador]] = field(default_factory=dict)
    nomes: dict[str, str] = field(default_factory=dict)
    plus: list[Plu] = field(default_factory=list)

    def categorias(self, cod_sap) -> list[CategoriaPrestador]:
        return self.prestadores.get(_codigo(cod_sap), [])

    def plus_de(self, serv: str, categoria: int) -> list[Plu]:
        return [p for p in self.plus if p.serv == serv and p.categoria == categoria]

    def servs(self) -> dict[str, str]:
        """SERV -> descrição do item da LC 116 (serve para achar o código pela descrição na nota)."""
        return {p.serv: p.descricao_116 for p in self.plus}


def _codigo(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip().lstrip("0")


def _inteiro(valor) -> int | None:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def _ler_abas(caminho: Path, abas: list[str]) -> dict[str, list[list]]:
    dados: dict[str, list[list]] = {}
    if caminho.suffix.lower() == ".xlsb":
        from pyxlsb import open_workbook

        with open_workbook(str(caminho)) as wb:
            for aba in abas:
                if aba not in wb.sheets:
                    raise ValueError(f"{caminho.name}: aba '{aba}' não encontrada (abas: {', '.join(wb.sheets)})")
                with wb.get_sheet(aba) as folha:
                    dados[aba] = [[c.v for c in linha] for linha in folha.rows()]
    else:
        from openpyxl import load_workbook

        wb = load_workbook(caminho, read_only=True, data_only=True)
        for aba in abas:
            if aba not in wb.sheetnames:
                raise ValueError(f"{caminho.name}: aba '{aba}' não encontrada (abas: {', '.join(wb.sheetnames)})")
            dados[aba] = [list(linha) for linha in wb[aba].iter_rows(values_only=True)]
        wb.close()
    return dados


def _indices(cabecalho: list, esperadas: dict[str, list[str]], arquivo: str, aba: str) -> dict[str, int]:
    nomes = [normalizar(str(c or "").replace("|", "")) for c in cabecalho]
    indices = {}
    for campo, opcoes in esperadas.items():
        for opcao in opcoes:
            if normalizar(opcao) in nomes:
                indices[campo] = nomes.index(normalizar(opcao))
                break
        else:
            raise ValueError(f"{arquivo}, aba '{aba}': coluna '{opcoes[0]}' não encontrada")
    return indices


COLUNAS_PRESTADORES = {
    "cod": ["Cod SAP", "Código SAP"],
    "nome": ["Forn SAP", "Fornecedor"],
    "categoria": ["Ctg. Serv.", "Categoria"],
    "descricao": ["Desc. Ctg. Serv.", "Descrição Categoria"],
    "padrao": ["Padrão Tributação", "Padrao Tributacao"],
    "impostos": ["Impostos"],
}
COLUNAS_PLUS = {
    "plu": ["PLU"],
    "descricao": ["Descrição"],
    "serv": ["SERV"],
    "descricao_116": ["116"],
    "categoria": ["Categoria"],
    "descricao_categoria": ["Descrição Categoria"],
    "conta": ["Conta Contábil"],
    "descricao_conta": ["Descrição CC"],
}


def carregar(caminho: str | Path, aba_prestadores: str = "Prestadores x REINF", aba_plus: str = "PLUs") -> BaseFiscal:
    caminho = Path(caminho)
    dados = _ler_abas(caminho, [aba_prestadores, aba_plus])
    base = BaseFiscal()

    linhas = dados[aba_prestadores]
    idx = _indices(linhas[0], COLUNAS_PRESTADORES, caminho.name, aba_prestadores)
    for linha in linhas[1:]:
        cod = _codigo(linha[idx["cod"]] if idx["cod"] < len(linha) else None)
        categoria = _inteiro(linha[idx["categoria"]]) if idx["categoria"] < len(linha) else None
        if not cod or categoria is None:
            continue
        base.nomes.setdefault(cod, str(linha[idx["nome"]] or "").strip())
        cat = CategoriaPrestador(
            categoria=categoria,
            descricao=str(linha[idx["descricao"]] or "").strip(),
            padrao=str(linha[idx["padrao"]] or "").strip(),
            impostos=str(linha[idx["impostos"]] or "").strip(),
        )
        lista = base.prestadores.setdefault(cod, [])
        if cat not in lista:
            lista.append(cat)

    linhas = dados[aba_plus]
    idx = _indices(linhas[0], COLUNAS_PLUS, caminho.name, aba_plus)
    for linha in linhas[1:]:
        if not linha or linha[idx["plu"]] in (None, ""):
            continue
        base.plus.append(Plu(
            plu=_codigo(linha[idx["plu"]]),
            descricao=str(linha[idx["descricao"]] or "").strip(),
            serv=str(linha[idx["serv"]] or "").strip().upper(),
            descricao_116=str(linha[idx["descricao_116"]] or "").strip(),
            categoria=_inteiro(linha[idx["categoria"]]) or 0,
            descricao_categoria=str(linha[idx["descricao_categoria"]] or "").strip(),
            conta=_codigo(linha[idx["conta"]]),
            descricao_conta=str(linha[idx["descricao_conta"]] or "").strip(),
        ))
    if not base.prestadores or not base.plus:
        raise ValueError(f"{caminho.name}: base vazia (prestadores: {len(base.prestadores)}, PLUs: {len(base.plus)})")
    return base
