"""Processa uma pasta de notas e gera a planilha.

Exemplos:
    python cli.py exemplos
    python cli.py exemplos --saida saida/notas.xlsx --provedor claude
    python cli.py exemplos --provedor offline
"""

from __future__ import annotations

import argparse
import logging
import time

from dotenv import load_dotenv

load_dotenv()

from extrator import criar_provedor, extrair_nota  # noqa: E402
from extrator.exportar import salvar_excel  # noqa: E402
from extrator.leitor import ler_texto, listar_arquivos  # noqa: E402


def brl(valor) -> str:
    """1234.5 -> 'R$ 1.234,50'"""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrai dados de notas fiscais com IA e gera uma planilha.")
    parser.add_argument("entrada", help="Pasta com notas (.pdf/.txt) ou um arquivo")
    parser.add_argument("--saida", default="saida/notas_extraidas.xlsx", help="Planilha de destino")
    parser.add_argument("--provedor", choices=["gemini", "claude", "offline"], help="Sobrescreve LLM_PROVEDOR")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    provedor = criar_provedor(args.provedor)
    arquivos = listar_arquivos(args.entrada)
    print(f"Provedor: {provedor.nome} | {len(arquivos)} nota(s)\n")

    inicio = time.perf_counter()
    resultados = []
    for caminho in arquivos:
        try:
            texto = ler_texto(caminho)
        except ValueError as erro:
            print(f"  [ERRO]    {caminho.name}: {erro}")
            continue
        r = extrair_nota(texto, provedor, arquivo=caminho.name)
        resultados.append(r)
        valor = brl(r.nota.valor_total) if r.nota.valor_total is not None else "-"
        print(f"  [{r.status:<7}] {caminho.name:<32} {(r.nota.fornecedor or '-')[:38]:<38} {valor:>14}")
        for motivo in r.motivos:
            print(f"              -> {motivo}")

    if resultados:
        destino = salvar_excel(resultados, args.saida)
        ok = sum(r.status == "OK" for r in resultados)
        print(f"\n{ok} OK, {len(resultados) - ok} para revisar em {time.perf_counter() - inicio:.1f}s")
        print(f"Planilha: {destino}")


if __name__ == "__main__":
    main()
