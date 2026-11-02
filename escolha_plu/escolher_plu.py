"""Preenche o PLU (coluna Componente) da planilha das OMs a partir das NFS-e e da base fiscal.

Dia a dia: dois cliques em executar.bat (ou `python escolher_plu.py`). Tudo vem do config.json.

Para cada linha da planilha:
  1. acha o PDF da nota pela ocorrência (e baixa pelo SAP os que faltarem, se ligado no config)
  2. lê no PDF o código de serviço e as retenções federais
  3. cruza com a base fiscal (categorias liberadas para o fornecedor + aba PLUs)
  4. preenche o PLU, ou deixa a linha em amarelo com o motivo

O resultado é uma CÓPIA da planilha (com a macro VBA preservada), pronta para rodar a macro da IW32.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from plu import base_fiscal, planilha_om
from plu.escolha import Escolha, escolher
from plu.leitor_pdf import ler_nota

PASTA = Path(__file__).resolve().parent


def carregar_config() -> tuple[dict, Path]:
    caminho = PASTA / "config.json"
    if not caminho.exists():
        raise ValueError("config.json não encontrado. Copie config.exemplo.json para config.json e ajuste os caminhos.")
    try:
        cfg = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise ValueError(f"config.json com erro na linha {erro.lineno}: {erro.msg}. "
                         "Em caminhos do Windows use / ou \\\\.") from erro
    return cfg, caminho


def caminho(cfg: dict, chave: str, obrigatorio: bool = True) -> Path | None:
    valor = cfg.get(chave)
    if not valor:
        if obrigatorio:
            raise ValueError(f'"{chave}" não preenchido no config.json')
        return None
    p = Path(valor)
    return p if p.is_absolute() or str(valor).startswith(("\\\\", "//")) else PASTA / p


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
    cfg, _ = carregar_config()
    planilha = caminho(cfg, "planilha_om")
    base_arq = caminho(cfg, "base_fiscal")
    pasta_pdfs = caminho(cfg, "pasta_pdfs")
    for p, nome in ((planilha, "planilha_om"), (base_arq, "base_fiscal")):
        if not p.is_file():
            raise ValueError(f"{nome} não encontrado: {p}")
    pasta_pdfs.mkdir(parents=True, exist_ok=True)

    print("Carregando a base fiscal...")
    base = base_fiscal.carregar(base_arq)
    print(f"  {len(base.prestadores)} fornecedores · {len(base.plus)} PLUs")
    linhas = planilha_om.ler(planilha, cfg.get("aba_om"))
    print(f"Planilha: {planilha.name} · {len(linhas)} OM(s)\n")

    baixar = cfg.get("baixar_notas", {})
    if baixar.get("usar"):
        faltando = sorted({l.ocorrencia for l in linhas if l.ocorrencia and not achar_pdf(pasta_pdfs, l.ocorrencia)})
        if faltando:
            print(f"Baixando {len(faltando)} nota(s) pela macro baixar_nota (deixe o SAP aberto e logado)...")
            from plu.baixar import baixar_faltantes
            baixar_faltantes(caminho(cfg, "pasta_macro_baixar_nota"), pasta_pdfs, faltando)

    de_para = {re.sub(r"\D", "", k).lstrip("0"): v for k, v in cfg.get("codigos_municipais", {}).items()}
    descricoes = base.servs()
    notas_lidas: dict[str, object] = {}
    resultados: list[tuple[planilha_om.LinhaOM, Escolha]] = []

    for linha in linhas:
        pdf = achar_pdf(pasta_pdfs, linha.ocorrencia)
        nota = None
        if pdf:
            if pdf not in notas_lidas:
                try:
                    notas_lidas[pdf] = ler_nota(pdf, descricoes)
                except Exception as erro:  # noqa: BLE001 - PDF corrompido não pode parar o lote
                    notas_lidas[pdf] = erro
            nota = notas_lidas[pdf]
            if isinstance(nota, Exception):
                resultados.append((linha, Escolha("REVISAR", motivo=f"PDF ilegível: {nota}")))
                continue
            if not nota.item_lc116 and nota.codigo_municipal:
                item = de_para.get(nota.codigo_municipal.lstrip("0"))
                if item:
                    nota.item_lc116 = item
        escolha = escolher(base, linha.fornecedor, nota, linha.preco,
                           plu_preferido=cfg.get("plu_preferido"), contas_preferidas=cfg.get("contas_preferidas"))
        resultados.append((linha, escolha))
        print(f"  [{escolha.status:<7}] OM {linha.om:<10} forn {linha.fornecedor:<8} "
              f"ocor {linha.ocorrencia or '-':<11} PLU {escolha.plu or '-':<9} {escolha.motivo[:90]}")

    destino = caminho(cfg, "pasta_saida", obrigatorio=False) or PASTA / "saida"
    destino = destino / f"{planilha.stem}_PLU_{datetime.now():%Y-%m-%d_%H%M}{planilha.suffix}"
    salvo = planilha_om.salvar(planilha, destino, resultados, cfg.get("aba_om"), cfg.get("se_revisar", "limpar"))

    ok = sum(e.status == "OK" for _, e in resultados)
    print(f"\n{ok} OM(s) com PLU preenchido · {len(resultados) - ok} para revisar (em amarelo) "
          f"· {time.perf_counter() - inicio:.1f}s")
    print(f"Planilha pronta para a macro: {salvo}")
    if len(resultados) - ok:
        print("Antes de rodar a macro da IW32, preencha ou apague as linhas em amarelo.")
    if cfg.get("abrir_planilha", True) and hasattr(os, "startfile"):
        os.startfile(salvo)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as erro:
        print(f"\n✖ {erro}")
        sys.exit(1)
