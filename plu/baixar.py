"""Baixa os PDFs que faltam usando a macro baixar_nota (SAP, transação NIXNFSE).

Reaproveita a função baixar_notas_sap da macro, sem copiar o código: carrega o main.py dela.
Cada PDF é salvo com o número da ocorrência no nome (ex.: 123456789.pdf).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def baixar_faltantes(pasta_macro: str | Path, pasta_pdfs: str | Path, ocorrencias: list[str]) -> None:
    pasta_macro, pasta_pdfs = Path(pasta_macro), Path(pasta_pdfs)
    arquivo = pasta_macro / "main.py"
    if not arquivo.is_file():
        raise ValueError(f"Macro baixar_nota não encontrada em {arquivo}")

    os.environ["PASTA_DESTINO"] = str(pasta_pdfs)        # antes de carregar: a macro lê isso ao iniciar
    spec = importlib.util.spec_from_file_location("baixar_nota_main", arquivo)
    modulo = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(pasta_macro))
    spec.loader.exec_module(modulo)
    modulo.PASTA_DESTINO = str(pasta_pdfs)

    registros = [{"linha": i, "ocorrencia": o, "ocorrencia_bruta": o, "nota": o,
                  "nome_unico": o, "duplicada": False} for i, o in enumerate(ocorrencias, start=1)]
    modulo.baixar_notas_sap(registros)
