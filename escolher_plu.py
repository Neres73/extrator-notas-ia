"""Preenche o PLU (coluna Componente) da planilha das OMs a partir das NFS-e e da base fiscal.

Dia a dia: dois cliques em executar.bat (ou `python escolher_plu.py`).
Tudo vem do config.json. Sem ele, roda com os exemplos fictícios (config.exemplo.json).
"""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from plu import planilha_om
from plu.escolha import Escolha
from plu.servico import analisar, carregar_json, montar, resolver

PASTA = Path(__file__).resolve().parent


def achar_pdf(pasta: Path, ocorrencia: str | None) -> Path | None:
    if not ocorrencia:
        return None
    exato = pasta / f"{ocorrencia}.pdf"
    if exato.is_file():
        return exato
    for pdf in pasta.glob("*.pdf"):
        if ocorrencia in re.sub(r"\D", " ", pdf.stem).split():
            return pdf
    return None


def main() -> int:
    inicio = time.perf_counter()
    try:
        from dotenv import load_dotenv
        load_dotenv(PASTA / ".env")
    except ImportError:
        pass

    arquivo_cfg = PASTA / "config.json"
    if not arquivo_cfg.exists():
        print("config.json não encontrado: rodando com os EXEMPLOS fictícios (config.exemplo.json).\n")
        arquivo_cfg = PASTA / "config.exemplo.json"
    cfg = carregar_json(arquivo_cfg)

    planilha = resolver(PASTA, cfg.get("planilha_om"))
    pasta_pdfs = resolver(PASTA, cfg.get("pasta_pdfs"))
    if not planilha or not planilha.is_file():
        raise ValueError(f"Planilha das OMs não encontrada: {planilha}")
    if not pasta_pdfs:
        raise ValueError('"pasta_pdfs" não preenchido no config')
    pasta_pdfs.mkdir(parents=True, exist_ok=True)

    print("Carregando a base fiscal...")
    conf = montar(cfg, PASTA)
    print(f"  {len(conf.base.prestadores)} fornecedores · {len(conf.base.plus)} PLUs · "
          f"IA de reserva: {conf.provedor_ia.nome if conf.provedor_ia else 'desligada'}")
    linhas = planilha_om.ler(planilha, cfg.get("aba_om"))
    print(f"Planilha: {planilha.name} · {len(linhas)} OM(s)\n")

    if cfg.get("baixar_notas", {}).get("usar"):
        faltando = sorted({l.ocorrencia for l in linhas if l.ocorrencia and not achar_pdf(pasta_pdfs, l.ocorrencia)})
        if faltando:
            print(f"Baixando {len(faltando)} nota(s) pela macro baixar_nota (deixe o SAP aberto e logado)...")
            from plu.baixar import baixar_faltantes
            baixar_faltantes(resolver(PASTA, cfg.get("pasta_macro_baixar_nota")), pasta_pdfs, faltando)

    cache: dict[Path, tuple] = {}
    resultados: list[tuple[planilha_om.LinhaOM, Escolha]] = []
    for linha in linhas:
        pdf = achar_pdf(pasta_pdfs, linha.ocorrencia)
        chave = (pdf, linha.fornecedor)
        if chave not in cache:
            cache[chave] = analisar(pdf, linha.fornecedor, linha.preco, conf)
        escolha, _ = cache[chave]
        resultados.append((linha, escolha))
        print(f"  [{escolha.status:<7}] OM {linha.om:<10} ocor {linha.ocorrencia or '-':<11} "
              f"PLU {escolha.plu or '-':<9} {escolha.motivo[:95]}")

    destino = (resolver(PASTA, cfg.get("pasta_saida")) or PASTA / "saida")
    destino = destino / f"{planilha.stem}_PLU_{datetime.now():%Y-%m-%d_%H%M}{planilha.suffix}"
    salvo = planilha_om.salvar(planilha, destino, resultados, cfg.get("aba_om"), cfg.get("se_revisar", "limpar"))

    ok = sum(e.status == "OK" for _, e in resultados)
    print(f"\n{ok} OM(s) com PLU preenchido · {len(resultados) - ok} para revisar (em amarelo) "
          f"· {time.perf_counter() - inicio:.1f}s")
    print(f"Planilha pronta para a macro: {salvo}")
    if len(resultados) - ok:
        print("Antes de rodar a macro da IW32, resolva as linhas em amarelo.")
    if cfg.get("abrir_planilha", True) and hasattr(os, "startfile"):
        os.startfile(salvo)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as erro:
        print(f"\n✖ {erro}")
        sys.exit(1)
