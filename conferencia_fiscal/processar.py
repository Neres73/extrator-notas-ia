"""Confere as NFS-e contra a base de parâmetros fiscais e gera os pedidos de correção.

Exemplos:
    python processar.py --xml exemplos/xml --parametros exemplos/parametros_fiscais_exemplo.xlsx
    python processar.py --xml \\\\servidor\\xml_nfse --parametros base.xlsx --fila fila_nfse.xlsx
    python processar.py ... --sap                # mostra o que seria lançado (simulação)
    python processar.py ... --sap --lancar       # lança de verdade no SAP
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime

from correcao_nfse.config import Config
from correcao_nfse.planilhas import BaseParametros, carregar_fila
from correcao_nfse.processamento import processar
from correcao_nfse.relatorio import salvar
from correcao_nfse.utils import moeda


def main() -> None:
    p = argparse.ArgumentParser(description="Gera pedidos de correção a partir das NFS-e e da base de parâmetros.")
    p.add_argument("--xml", required=True, help="Pasta com os XMLs das NFS-e (procura em subpastas também)")
    p.add_argument("--parametros", required=True, help="Planilha da base de parâmetros fiscais")
    p.add_argument("--fila", help="Planilha da fila/base de NFS-e (opcional; sem ela, confere todos os XMLs)")
    p.add_argument("--config", help="config.json com nomes de colunas e limites (opcional)")
    p.add_argument("--saida", default=f"saida/correcao_nfse_{datetime.now():%Y-%m-%d_%H%M}.xlsx")
    p.add_argument("--sap", action="store_true", help="Passa os pedidos de correção para a etapa do SAP")
    p.add_argument("--lancar", action="store_true", help="Com --sap: lança de verdade (sem isso, só simula)")
    args = p.parse_args()

    inicio = time.perf_counter()
    config = Config.carregar(args.config)
    base = BaseParametros.carregar(args.parametros, config)
    fila = carregar_fila(args.fila, config) if args.fila else None
    print(f"Base de parâmetros: {len(base.parametros)} linha(s)" + (f" | Fila: {len(fila)} nota(s)" if fila else ""))

    lote = processar(args.xml, base, config, fila)
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

    destino = salvar(lote, args.saida)
    print(f"\n{lote.contar('OK')} OK · {lote.contar('CORRIGIR')} para corrigir · "
          f"{lote.contar('REVISAR') + len(lote.arquivos_invalidos)} para revisar "
          f"({time.perf_counter() - inicio:.1f}s)")
    print(f"Planilha: {destino}")

    if args.sap:
        from correcao_nfse.sap import lancar
        lancar(lote.resultados, simulacao=not args.lancar)


if __name__ == "__main__":
    main()
