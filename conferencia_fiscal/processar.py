"""Roda o processo inteiro: lê os XMLs, confere com a base fiscal, gera a planilha e passa para o SAP.

Uso no dia a dia: dois cliques em executar.bat (ou `python processar.py`).
Tudo vem do config.json: pastas, planilhas e o modo do SAP ("nao", "simular" ou "lancar").
Sem config.json, roda com os arquivos de exemplo (config.exemplo.json).

Os argumentos abaixo são opcionais e só servem para sobrescrever o config numa execução pontual:
    python processar.py --fila outra_fila.xlsx
    python processar.py --sap nao
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from correcao_nfse.config import Config
from correcao_nfse.planilhas import BaseParametros, carregar_fila
from correcao_nfse.processamento import processar
from correcao_nfse.relatorio import salvar
from correcao_nfse.utils import moeda

PASTA = Path(__file__).resolve().parent


def escolher_config(indicado: str | None) -> Path:
    if indicado:
        return Path(indicado)
    if (PASTA / "config.json").exists():
        return PASTA / "config.json"
    print("config.json não encontrado: rodando com os EXEMPLOS (config.exemplo.json).")
    print("Para usar os arquivos reais, copie config.exemplo.json para config.json e ajuste os caminhos.\n")
    return PASTA / "config.exemplo.json"


def conferir_caminhos(config: Config) -> list[str]:
    erros = []
    if not config.pasta_xml or not config.pasta_xml.is_dir():
        erros.append(f"Pasta de XMLs não encontrada: {config.pasta_xml or '(não informada em entrada.pasta_xml)'}")
    if not config.parametros or not config.parametros.is_file():
        erros.append(f"Base de parâmetros não encontrada: {config.parametros or '(não informada em entrada.parametros)'}")
    if config.fila and not config.fila.is_file():
        erros.append(f"Planilha da fila não encontrada: {config.fila}")
    return erros


def executar(args: argparse.Namespace) -> int:
    inicio = time.perf_counter()
    caminho_config = escolher_config(args.config)
    config = Config.carregar(caminho_config)
    if args.xml:
        config.pasta_xml = Path(args.xml)
    if args.parametros:
        config.parametros = Path(args.parametros)
    if args.fila:
        config.fila = Path(args.fila)
    if args.sap:
        config.sap = args.sap

    erros = conferir_caminhos(config)
    if erros:
        print("Não foi possível começar:")
        for e in erros:
            print(f"  ✖ {e}")
        print(f"\nAjuste os caminhos em {caminho_config.name} e rode de novo.")
        return 1

    base = BaseParametros.carregar(config.parametros, config)
    fila = carregar_fila(config.fila, config) if config.fila else None
    print(f"XMLs: {config.pasta_xml}")
    print(f"Base de parâmetros: {len(base.parametros)} linha(s)" + (f" | Fila: {len(fila)} nota(s)" if fila else
                                                                     " | Sem fila: conferindo todos os XMLs"))
    print()

    lote = processar(config.pasta_xml, base, config, fila)
    for r in lote.resultados:
        n = r.nota
        nome = (n.nome_prestador if n else "") or ""
        numero = n.numero if n else (r.fila.numero_nota if r.fila else "?")
        valor = moeda(n.valor_servicos) if n else "-"
        print(f"  [{r.status:<8}] NFS-e {numero:<8} {nome[:34]:<34} {valor:>14}  PLU {r.plu_correto or '-'}")
        for m in r.motivos:
            print(f"               - {m}")
    for arquivo, motivo in lote.arquivos_invalidos:
        print(f"  [XML ✖   ] {arquivo}: {motivo}")

    destino = salvar(lote, config.pasta_saida / f"correcao_nfse_{datetime.now():%Y-%m-%d_%H%M}.xlsx")
    print(f"\n{lote.contar('OK')} OK · {lote.contar('CORRIGIR')} para corrigir · "
          f"{lote.contar('REVISAR') + len(lote.arquivos_invalidos)} para revisar "
          f"({time.perf_counter() - inicio:.1f}s)")
    print(f"Planilha: {destino}")

    if config.sap != "nao" and lote.contar("CORRIGIR"):
        from correcao_nfse.sap import lancar
        try:
            lancar(lote.resultados, simulacao=config.sap != "lancar")
        except NotImplementedError as aviso:
            print(f"\n⚠ SAP: {aviso}")
            print('  Nada foi lançado. Enquanto isso, deixe "sap": "simular" no config.json.')
        except RuntimeError as erro:
            print(f"\n✖ SAP: {erro}")

    if config.abrir_planilha and hasattr(os, "startfile"):
        os.startfile(destino)  # abre no Excel (só existe no Windows)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Confere as NFS-e com a base fiscal e gera os pedidos de correção.")
    p.add_argument("--config", help="Outro arquivo de configuração (padrão: config.json)")
    p.add_argument("--xml", help="Sobrescreve entrada.pasta_xml")
    p.add_argument("--parametros", help="Sobrescreve entrada.parametros")
    p.add_argument("--fila", help="Sobrescreve entrada.fila")
    p.add_argument("--sap", choices=["nao", "simular", "lancar"], help="Sobrescreve o modo do SAP")
    try:
        codigo = executar(p.parse_args())
    except (ValueError, OSError) as erro:
        print(f"\n✖ {erro}")
        codigo = 1
    sys.exit(codigo)


if __name__ == "__main__":
    main()
