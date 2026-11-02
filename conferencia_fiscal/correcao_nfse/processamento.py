"""Junta tudo: lê os XMLs, liga com a fila (se houver), consulta a base e aplica as regras."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .leitor_nfse import XmlInvalido, ler_arquivo
from .nota import NotaServico
from .planilhas import BaseParametros, LinhaFila, chave_nota
from .regras import Resultado, conferir, sem_xml


@dataclass
class Lote:
    resultados: list[Resultado] = field(default_factory=list)
    arquivos_invalidos: list[tuple[str, str]] = field(default_factory=list)   # (arquivo, motivo)

    def contar(self, status: str) -> int:
        return sum(r.status == status for r in self.resultados)


def ler_pasta(pasta: str | Path) -> tuple[dict[tuple[str, str], list[NotaServico]], list[tuple[str, str]]]:
    """Lê todos os .xml da pasta (e subpastas). Devolve as notas indexadas por (CNPJ, número)."""
    indice: dict[tuple[str, str], list[NotaServico]] = {}
    invalidos = []
    for caminho in sorted(Path(pasta).rglob("*")):
        if caminho.suffix.lower() != ".xml" or not caminho.is_file():
            continue
        try:
            notas = ler_arquivo(caminho)
        except XmlInvalido as erro:
            invalidos.append((caminho.name, str(erro)))
            continue
        for nota in notas:
            indice.setdefault(chave_nota(nota.cnpj_prestador, nota.numero), []).append(nota)
    return indice, invalidos


def processar(pasta_xml: str | Path, base: BaseParametros, config: Config,
              fila: list[LinhaFila] | None = None) -> Lote:
    indice, invalidos = ler_pasta(pasta_xml)
    lote = Lote(arquivos_invalidos=invalidos)

    def avaliar(nota: NotaServico, linha: LinhaFila | None) -> Resultado:
        return conferir(nota, base.buscar(nota.item_lc116, nota.codigo_municipal), config, linha)

    if fila is None:
        # sem fila: confere todas as notas encontradas na pasta
        for notas in indice.values():
            for nota in notas:
                lote.resultados.append(avaliar(nota, None))
        return lote

    for linha in fila:
        notas = indice.get(linha.chave, [])
        if not notas and linha.arquivo_xml:
            caminho = Path(linha.arquivo_xml)
            if not caminho.is_absolute():
                caminho = Path(pasta_xml) / caminho
            try:
                notas = ler_arquivo(caminho)
            except (OSError, XmlInvalido) as erro:
                lote.resultados.append(sem_xml(linha, f"XML indicado na fila não pôde ser lido: {erro}"))
                continue
        if not notas:
            lote.resultados.append(sem_xml(
                linha, f"XML da nota {linha.numero_nota} (CNPJ {linha.cnpj_prestador}) não encontrado na pasta"))
        elif len(notas) > 1:
            arquivos = ", ".join(n.arquivo for n in notas)
            lote.resultados.append(sem_xml(linha, f"Mais de um XML para a mesma nota: {arquivos}"))
        else:
            lote.resultados.append(avaliar(notas[0], linha))
    return lote
