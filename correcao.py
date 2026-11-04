"""Processo completo das OMs de correção, partindo só da Base Geral.

1. Base Geral -> filtra time, filas e valor máximo
2. Baixa os PDFs que faltam (macro baixar_nota) e escolhe o PLU de cada nota (base fiscal)
   -> só segue quem tem PLU certo; o resto vai para o relatório com o motivo
3. ME2K com os pedidos -> ordem original de cada pedido
4. Monta a planilha de criação em massa ('REA ordem' + ordem, centro de custo, local, campos fixos)
5. Carrega na transação de criação -> OMs novas, ligadas a cada linha pelo nº do Registro
6. IW32 em cada OM nova: fornecedor, PLU, preço e requisitante (mesmos passos da macro da teste om)

Tudo vem do config.json (seção "correcao"). Dia a dia: executar_correcao.bat.
No fim sai um relatório com o que aconteceu com cada ocorrência.
"""

from __future__ import annotations

import csv
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from escolher_plu import achar_pdf
from plu import base_geral, input_om
from plu.base_geral import Ocorrencia
from plu.servico import analisar, carregar_json, montar, resolver

PASTA = Path(__file__).resolve().parent
VERDE = PatternFill("solid", start_color="C6EFCE")
AMARELO = PatternFill("solid", start_color="FFEB9C")
VERMELHO = PatternFill("solid", start_color="FFC7CE")


@dataclass
class Item:
    oc: Ocorrencia
    etapa: str = "Filtro"
    status: str = "PENDENTE"           # PENDENTE / REVISAR / ERRO / CONCLUIDO
    motivo: str = ""
    plu: str | None = None
    ordem_original: str | None = None
    om_nova: str | None = None
    nota_nova: str | None = None
    mensagens: list[str] = field(default_factory=list)

    def parar(self, etapa: str, status: str, motivo: str) -> None:
        self.etapa, self.status, self.motivo = etapa, status, motivo


def lotes(itens: list, tamanho: int):
    for i in range(0, len(itens), tamanho):
        yield itens[i:i + tamanho]


def ligar_registros(lote: list[Item], registros) -> None:
    """Registro N do relatório = linha N da planilha enviada."""
    por_numero = {r.registro: r for r in registros}
    for n, item in enumerate(lote, start=1):
        r = por_numero.get(n)
        if r is None:
            item.parar("Criação da OM", "ERRO", "Linha não apareceu no relatório da transação")
        elif not r.ok:
            item.parar("Criação da OM", "ERRO", f"Transação recusou: {r.descricao}")
        else:
            item.om_nova, item.nota_nova, item.etapa = r.ordem, r.nota, "OM criada"


def salvar_teste_om(modelo: Path | None, destino: Path, itens: list[Item], cfg: dict) -> Path:
    """Registro no formato da planilha teste om (serve também para rodar a macro antiga se precisar)."""
    if modelo and modelo.is_file():
        wb = load_workbook(modelo, keep_vba=modelo.suffix.lower() == ".xlsm")
        ws = wb.worksheets[0]
        for linha in ws.iter_rows(min_row=2):                # começa do zero: só o cabeçalho fica
            for cel in linha:
                cel.value = None
        if ws.max_row > 1:
            ws.delete_rows(2, ws.max_row)
        destino = destino.with_suffix(modelo.suffix)
    else:
        wb = Workbook()
        ws = wb.active
        ws.append(["O.M", "Fornecedor", "Componente", "Qtd.necessária", "Preço", "Requisitante", "TEXTO BREVE"])
    for col, titulo in ((8, "ocorrencia"), (9, "Status IW32")):
        ws.cell(row=1, column=col, value=titulo).font = Font(bold=True)
    for i, it in enumerate(itens, start=2):
        valores = [int(it.om_nova), int(it.oc.fornecedor) if it.oc.fornecedor.isdigit() else it.oc.fornecedor,
                   int(it.plu) if it.plu.isdigit() else it.plu, 1, float(it.oc.valor), cfg["requisitante"],
                   f"{cfg['prefixo_texto_breve']}{it.ordem_original}", it.oc.ocorrencia,
                   "OK" if it.status == "CONCLUIDO" else it.motivo]
        for col, v in enumerate(valores, start=1):
            ws.cell(row=i, column=col, value=v)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def salvar_relatorio(destino: Path, itens: list[Item]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório"
    cab = ["Ocorrência", "Pedido", "Fornecedor", "Valor", "Fila (Status)", "Centro", "PLU", "Ordem original",
           "OM nova", "Nota nova", "Etapa", "Resultado", "Motivo"]
    ws.append(cab)
    for c in ws[1]:
        c.font = Font(bold=True)
    for it in itens:
        ws.append([it.oc.ocorrencia, it.oc.pedido, it.oc.fornecedor, float(it.oc.valor or 0), it.oc.status,
                   it.oc.centro, it.plu, it.ordem_original, it.om_nova, it.nota_nova, it.etapa, it.status,
                   " | ".join([it.motivo, *it.mensagens]).strip(" |")])
        cor = {"CONCLUIDO": VERDE, "REVISAR": AMARELO, "ERRO": VERMELHO}.get(it.status)
        if cor:
            ws.cell(row=ws.max_row, column=12).fill = cor
    for letra, largura in {"A": 12, "B": 12, "E": 40, "K": 16, "M": 100}.items():
        ws.column_dimensions[letra].width = largura
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def ler_historico(arquivo: Path) -> dict[str, str]:
    """{ocorrência: 'OM 123 em 04/11/2026'} das execuções anteriores: impede criar OM duas vezes."""
    if not arquivo.is_file():
        return {}
    with arquivo.open(encoding="utf-8-sig", newline="") as f:
        return {ln["ocorrencia"]: f"OM {ln['om_nova']} em {ln['data']}" for ln in csv.DictReader(f, delimiter=";")}


def gravar_historico(arquivo: Path, itens: list[Item]) -> None:
    novo = not arquivo.is_file()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with arquivo.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["ocorrencia", "pedido", "ordem_original", "om_nova", "nota_nova", "plu", "data"])
        for it in itens:
            w.writerow([it.oc.ocorrencia, it.oc.pedido, it.ordem_original, it.om_nova, it.nota_nova, it.plu,
                        f"{datetime.now():%d/%m/%Y %H:%M}"])


def confirmar(pergunta: str) -> bool:
    return input(f"{pergunta} [s/N] ").strip().lower() in ("s", "sim")


def main() -> int:
    inicio = time.perf_counter()
    try:
        from dotenv import load_dotenv
        load_dotenv(PASTA / ".env")
    except ImportError:
        pass

    arquivo_cfg = PASTA / "config.json"
    if not arquivo_cfg.exists():
        raise ValueError("config.json não encontrado: copie config.exemplo.json e preencha a seção \"correcao\"")
    cfg = carregar_json(arquivo_cfg)
    cc = cfg.get("correcao")
    if not cc:
        raise ValueError('config.json sem a seção "correcao"')

    carimbo = f"{datetime.now():%Y-%m-%d_%H%M}"
    pasta_saida = resolver(PASTA, cfg.get("pasta_saida")) or PASTA / "saida"
    pasta_pdfs = resolver(PASTA, cfg.get("pasta_pdfs"))
    if not pasta_pdfs:
        raise ValueError('"pasta_pdfs" não preenchido no config')
    pasta_pdfs.mkdir(parents=True, exist_ok=True)

    # 1. Base Geral -------------------------------------------------------------------------
    base_arq = resolver(PASTA, cc["base_geral"])
    if not base_arq or not base_arq.is_file():
        raise ValueError(f"Base Geral não encontrada: {base_arq}")
    todas = base_geral.ler(base_arq, cc.get("aba_base", "Base"))
    maximo = Decimal(str(cc["valor_maximo"])) if cc.get("valor_maximo") is not None else None
    filtradas = base_geral.filtrar(todas, cc.get("filas", []), cc.get("time"), maximo)
    itens = [Item(o) for o in filtradas]
    print(f"Base Geral: {len(todas)} ocorrências · {len(itens)} no filtro "
          f"(time {cc.get('time')}, até R$ {maximo}, {len(cc.get('filas', []))} filas)")
    if not itens:
        print("Nada para processar.")
        return 0

    historico_arq = pasta_saida / "historico_correcao.csv"
    historico = ler_historico(historico_arq)
    por_pedido: dict[str, int] = {}
    for it in itens:
        por_pedido[it.oc.pedido] = por_pedido.get(it.oc.pedido, 0) + 1
    for it in itens:
        if it.oc.ocorrencia in historico:
            it.parar("Filtro", "REVISAR", f"OM de correção já criada para esta ocorrência ({historico[it.oc.ocorrencia]})")
        elif not it.oc.valor or it.oc.valor <= 0:
            it.parar("Filtro", "REVISAR", "Vlr Total zerado ou vazio na Base Geral")
        elif por_pedido[it.oc.pedido] > 1:
            it.mensagens.append(f"Aviso: pedido {it.oc.pedido} aparece em {por_pedido[it.oc.pedido]} ocorrências")
    itens_ativos = [i for i in itens if i.status == "PENDENTE"]

    # 2. PDFs e PLU -------------------------------------------------------------------------
    conf = montar(cfg, PASTA)
    faltando = sorted({i.oc.ocorrencia for i in itens_ativos if not achar_pdf(pasta_pdfs, i.oc.ocorrencia)})
    if faltando and cfg.get("baixar_notas", {}).get("usar"):
        print(f"Baixando {len(faltando)} nota(s) pela macro baixar_nota...")
        from plu.baixar import baixar_faltantes
        baixar_faltantes(resolver(PASTA, cfg.get("pasta_macro_baixar_nota")), pasta_pdfs, faltando)
    for it in itens_ativos:
        escolha, _ = analisar(achar_pdf(pasta_pdfs, it.oc.ocorrencia), it.oc.fornecedor, it.oc.valor, conf)
        if escolha.status == "OK":
            it.plu, it.etapa = escolha.plu, "PLU"
        else:
            extra = (" | Opções: " + " / ".join(escolha.opcoes)) if escolha.opcoes else ""
            it.parar("PLU", "REVISAR", escolha.motivo + extra)
    seguem = [i for i in itens_ativos if i.status == "PENDENTE"]
    print(f"PLU: {len(seguem)} com PLU definido · {len(itens_ativos) - len(seguem)} para revisar")

    from plu import sap
    s = sap.sessao() if seguem else None

    # 3. ME2K -------------------------------------------------------------------------------
    if seguem:
        ordens = sap.ordens_dos_pedidos(s, sorted({i.oc.pedido for i in seguem}))
        for it in seguem:
            achadas = ordens.get(it.oc.pedido, [])
            distintas = sorted({o for o, _ in achadas})
            if not distintas:
                it.parar("ME2K", "REVISAR", "Pedido sem ordem (AUFNR) na ME2K")
            elif len(distintas) > 1:
                it.parar("ME2K", "REVISAR", f"Pedido com mais de uma ordem na ME2K: {', '.join(distintas)}")
            else:
                it.ordem_original = distintas[0]
                centros = {c for o, c in achadas if c}
                if centros and it.oc.centro.lstrip("0") not in centros:
                    it.mensagens.append(f"Aviso: centro da Base ({it.oc.centro}) diferente do centro de custo "
                                        f"do pedido na ME2K ({', '.join(sorted(centros))})")
        seguem = [i for i in seguem if i.status == "PENDENTE"]
        print(f"ME2K: {len(seguem)} com ordem original")

    # 4 e 5. Criação das OMs ----------------------------------------------------------------
    modelo = resolver(PASTA, cc["modelo_input"])
    locais, capacidade = input_om.ler_modelo(modelo)
    situacao: dict[str, str] = {}
    regioes = resolver(PASTA, cc.get("planilha_regioes"))
    if regioes and regioes.is_file():                     # mais atualizada que a Base Locais do modelo
        for centro, (local, status) in input_om.ler_regioes(regioes).items():
            locais[centro], situacao[centro] = local, status
    for it in seguem:
        if it.oc.centro not in locais:
            it.parar("Planilha de criação", "REVISAR",
                     f"Centro {it.oc.centro} sem local de instalação (planilha de regiões e Base Locais)")
        elif "fechad" in situacao.get(it.oc.centro, "").lower():
            it.mensagens.append(f"Aviso: loja {it.oc.centro} consta como '{situacao[it.oc.centro]}' nas regiões")
    seguem = [i for i in seguem if i.status == "PENDENTE"]
    if seguem and capacidade < 1:
        raise ValueError("A aba Input do modelo não tem linhas com fórmula")

    for n, lote in enumerate(lotes(seguem, capacidade), start=1):
        linhas = [input_om.montar_linha(f"{cc['prefixo_texto_breve']}{it.ordem_original}", it.oc.centro,
                                        locais[it.oc.centro], cc["campos_fixos"]) for it in lote]
        arquivo = input_om.preencher(modelo, pasta_saida / f"INPUT_OM_{carimbo}_lote{n}.xlsx", linhas)
        print(f"\nLote {n}: {len(lote)} linha(s) em {arquivo.name}")
        if cc.get("confirmar_antes_de_criar", True) and not confirmar(
                f"Criar {len(lote)} OM(s) na {cc['transacao_criacao']} agora?"):
            for it in lote:
                it.parar("Criação da OM", "REVISAR", f"Criação não confirmada (planilha pronta: {arquivo.name})")
            continue
        try:
            registros = sap.criar_oms(s, cc["transacao_criacao"], str(arquivo))
        except Exception as erro:  # noqa: BLE001
            for it in lote:
                it.parar("Criação da OM", "ERRO", f"{erro} (planilha: {arquivo.name}) - confira no SAP antes de rodar de novo")
            continue
        ligar_registros(lote, registros)
        gravar_historico(historico_arq, [it for it in lote if it.om_nova])   # já, antes da IW32
        print(f"  {sum(1 for it in lote if it.om_nova)} OM(s) criada(s)")

    criadas = [i for i in seguem if i.om_nova]

    # 6. IW32 -------------------------------------------------------------------------------
    iw = cc["iw32"]
    if criadas and iw.get("executar", True):
        print(f"\nIW32: preenchendo {len(criadas)} OM(s)...")
        for k, it in enumerate(criadas):
            try:
                msg = sap.preencher_componente(s, it.om_nova, it.oc.fornecedor, it.plu, it.oc.valor,
                                               iw["requisitante"], iw["grupo_compras"], iw["org_compras"])
                it.etapa, it.status = "IW32", "CONCLUIDO"
                if msg:
                    it.mensagens.append(msg)
                print(f"  [OK]   OM {it.om_nova} PLU {it.plu}")
            except Exception as erro:  # noqa: BLE001
                # tela em estado desconhecido: para aqui em vez de seguir lançando em cima
                it.parar("IW32", "ERRO", f"IW32 parou nesta OM: {erro}")
                for resto in criadas[k + 1:]:
                    resto.parar("IW32", "PENDENTE", "IW32 não rodou (parou numa OM anterior)")
                print(f"  [ERRO] OM {it.om_nova}: {erro}\n  IW32 interrompida; as OMs restantes estão no arquivo da teste om.")
                break
    for it in criadas:
        if it.status == "PENDENTE" and it.etapa == "OM criada":
            it.motivo = "OM criada; IW32 desligada no config"

    # Arquivos de saída ---------------------------------------------------------------------
    if criadas:                           # teste om do zero: só as OMs criadas nesta execução
        teste = salvar_teste_om(resolver(PASTA, cc.get("modelo_teste_om")),
                                pasta_saida / f"teste_om_{carimbo}.xlsx", criadas,
                                {"requisitante": iw["requisitante"], "prefixo_texto_breve": cc["prefixo_texto_breve"]})
        faltam = sum(1 for i in criadas if i.status != "CONCLUIDO")
        print(f"\nTeste om: {len(criadas)} OM(s), {faltam} sem componente na IW32 (coluna Status IW32): {teste}")
    rel = salvar_relatorio(pasta_saida / f"relatorio_correcao_{carimbo}.xlsx", itens)

    contagem = {st: sum(1 for i in itens if i.status == st) for st in ("CONCLUIDO", "REVISAR", "ERRO", "PENDENTE")}
    print(f"\n{contagem['CONCLUIDO']} concluída(s) · {contagem['REVISAR']} para revisar · "
          f"{contagem['ERRO']} com erro · {contagem['PENDENTE']} pendente(s) · {time.perf_counter() - inicio:.0f}s")
    print(f"Relatório: {rel}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError) as erro:
        print(f"\n✖ {erro}")
        sys.exit(1)
    except ImportError as erro:
        print(f"\n✖ Biblioteca não instalada ({erro.name}). No terminal, dentro da pasta do projeto, rode:\n"
              f'  "{sys.executable}" -m pip install -r requirements.txt')
        sys.exit(1)
