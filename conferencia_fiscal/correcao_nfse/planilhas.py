"""Leitura das planilhas de entrada: base de parâmetros fiscais e fila de NFS-e."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from .config import Config
from .utils import ZERO, decimal, item_lc116, so_digitos


def _normalizar(nome) -> str:
    texto = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    return "".join(c for c in texto.lower() if c.isalnum())


def _ler_tabela(caminho: str | Path, aba: str | None, colunas: dict[str, list[str]],
                obrigatorias: list[str]) -> list[dict]:
    """Lê a planilha achando o cabeçalho pelos nomes aceitos (procura nas 10 primeiras linhas)."""
    planilha = load_workbook(caminho, data_only=True, read_only=True)
    folha = planilha[aba] if aba else planilha.worksheets[0]
    linhas = list(folha.iter_rows(values_only=True))
    planilha.close()

    for indice_cab, cabecalho in enumerate(linhas[:10]):
        normalizados = [_normalizar(c) for c in cabecalho]
        mapa = {}
        for campo, nomes in colunas.items():
            for nome in nomes:
                if _normalizar(nome) in normalizados:
                    mapa[campo] = normalizados.index(_normalizar(nome))
                    break
        if all(c in mapa for c in obrigatorias):
            break
    else:
        faltando = ", ".join(f"{c} (aceita: {', '.join(colunas[c])})" for c in obrigatorias)
        raise ValueError(f"{Path(caminho).name}: não achei o cabeçalho com as colunas obrigatórias: {faltando}. "
                         "Ajuste os nomes no config.json.")

    registros = []
    for numero_linha, linha in enumerate(linhas[indice_cab + 1:], start=indice_cab + 2):
        if not any(v not in (None, "") for v in linha):
            continue
        registro = {campo: (linha[i] if i < len(linha) else None) for campo, i in mapa.items()}
        registro["_linha"] = numero_linha
        registros.append(registro)
    return registros


def _percentual(valor) -> Decimal:
    if valor in (None, ""):
        return ZERO
    if isinstance(valor, (int, float)):
        v = Decimal(str(valor))
        return v * 100 if ZERO < v < 1 else v     # célula formatada como % vem como fração
    return decimal(str(valor).replace("%", ""))


def _sim_nao(valor) -> bool | None:
    if valor in (None, ""):
        return None
    return _normalizar(valor) in ("s", "sim", "x", "true", "1", "retem", "retido")


# ---------------------------------------------------------------- base de parâmetros fiscais
@dataclass
class ParametroFiscal:
    linha: int
    item_lc116: str | None
    codigo_municipal: str | None
    descricao: str | None
    plu: str
    irrf: Decimal
    pcc: Decimal
    inss: Decimal
    retem_iss: bool | None


class BaseParametros:
    def __init__(self, parametros: list[ParametroFiscal]):
        self.parametros = parametros
        self._por_item: dict[str, list[ParametroFiscal]] = {}
        self._por_municipal: dict[str, list[ParametroFiscal]] = {}
        for p in parametros:
            if p.item_lc116:
                self._por_item.setdefault(p.item_lc116, []).append(p)
            if p.codigo_municipal:
                self._por_municipal.setdefault(so_digitos(p.codigo_municipal).lstrip("0"), []).append(p)

    @classmethod
    def carregar(cls, caminho: str | Path, config: Config) -> "BaseParametros":
        registros = _ler_tabela(caminho, config.aba_parametros, config.colunas_parametros, obrigatorias=["plu"])
        parametros = []
        for r in registros:
            plu = str(r.get("plu") or "").strip()
            if plu.endswith(".0"):
                plu = plu[:-2]
            if not plu:
                continue
            item = r.get("item_lc116")
            parametros.append(ParametroFiscal(
                linha=r["_linha"],
                item_lc116=item_lc116(str(item)) if item not in (None, "") else None,
                codigo_municipal=str(r["codigo_municipal"]).strip() if r.get("codigo_municipal") not in (None, "") else None,
                descricao=r.get("descricao"),
                plu=plu,
                irrf=_percentual(r.get("irrf")),
                pcc=_percentual(r.get("pcc")),
                inss=_percentual(r.get("inss")),
                retem_iss=_sim_nao(r.get("retem_iss")),
            ))
        if not parametros:
            raise ValueError(f"{Path(caminho).name}: nenhuma linha com PLU encontrada na base de parâmetros")
        return cls(parametros)

    def buscar(self, item: str | None, codigo_municipal: str | None) -> list[ParametroFiscal]:
        """Procura pelo item da LC 116; se não achar, pelo código municipal."""
        if item and item in self._por_item:
            return self._por_item[item]
        if codigo_municipal:
            return self._por_municipal.get(so_digitos(codigo_municipal).lstrip("0"), [])
        return []


# ---------------------------------------------------------------- fila de NFS-e
@dataclass
class LinhaFila:
    linha: int
    numero_nota: str | None
    cnpj_prestador: str | None
    ocorrencia: str | None
    pedido: str | None
    plu_atual: str | None
    arquivo_xml: str | None

    @property
    def chave(self) -> tuple[str, str]:
        return chave_nota(self.cnpj_prestador, self.numero_nota)


def chave_nota(cnpj: str | None, numero: str | None) -> tuple[str, str]:
    """(CNPJ só dígitos, número sem zeros à esquerda) — liga a linha da fila ao XML."""
    n = so_digitos(str(numero or "")).lstrip("0")
    c = so_digitos(cnpj)
    if 11 < len(c) < 14:          # CNPJ salvo como número no Excel perde os zeros à esquerda
        c = c.zfill(14)
    return c, n


def _texto(valor) -> str | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def carregar_fila(caminho: str | Path, config: Config) -> list[LinhaFila]:
    registros = _ler_tabela(caminho, config.aba_fila, config.colunas_fila,
                            obrigatorias=["numero_nota", "cnpj_prestador"])
    return [LinhaFila(
        linha=r["_linha"],
        numero_nota=_texto(r.get("numero_nota")),
        cnpj_prestador=_texto(r.get("cnpj_prestador")),
        ocorrencia=_texto(r.get("ocorrencia")),
        pedido=_texto(r.get("pedido")),
        plu_atual=_texto(r.get("plu_atual")),
        arquivo_xml=_texto(r.get("arquivo_xml")),
    ) for r in registros]
