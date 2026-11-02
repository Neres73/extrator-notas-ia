"""Gera os arquivos de exemplo, todos FICTÍCIOS: base fiscal, planilha das OMs e PDFs de NFS-e.

Os PDFs imitam os layouts que aparecem na fila (DANFSe nacional, Prefeitura de São Paulo,
prefeitura que só imprime o texto do item e um recibo em texto livre que só a IA entende).

Rodar:  python exemplos/gerar_exemplos.py   (precisa do reportlab)
"""

from __future__ import annotations

from pathlib import Path

PASTA = Path(__file__).resolve().parent

DESC_1401 = ("Lubrificação, limpeza, lustração, revisão, carga e recarga, conserto, restauração, blindagem, "
             "manutenção e conservação de máquinas, veículos, aparelhos, equipamentos, motores, elevadores")
DESC_0702 = ("Execução, por administração, empreitada ou subempreitada, de obras de construção civil, "
             "hidráulica ou elétrica e de outras obras semelhantes")


# ---------------------------------------------------------------- PDFs
def _pdf(destino: Path, linhas: list) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(destino), pagesize=A4)
    y = 800
    for item in linhas:
        if isinstance(item, list):           # várias colunas na mesma altura (tabela)
            for x, txt in item:
                c.drawString(x, y, txt)
        else:
            c.drawString(40, y, item)
        y -= 16
    c.save()
    return destino


def nacional(destino: Path, valor: str, irrf="0,00", cp="0,00", pcc="0,00",
             descricao="Manutenção corretiva em gerador", item="14.01.01", texto_item=DESC_1401):
    """Parecido com o DANFSe do padrão nacional."""
    return _pdf(destino, [
        "DANFSe v1.0 - Documento Auxiliar da NFS-e",
        "Número da NFS-e: 1207   Data e Hora da emissão: 20/10/2026 10:00",
        "SERVIÇO PRESTADO",
        f"Código de Tributação Nacional: {item} - {texto_item[:60]}",
        f"Descrição do Serviço: {descricao}",
        "TRIBUTAÇÃO FEDERAL",
        [(40, "IRRF"), (160, "Contribuição Previdenciária - Retida"), (380, "Contribuições Sociais - Retidas")],
        [(40, irrf), (160, cp), (380, pcc)],
        f"Valor do Serviço: R$ {valor}",
    ])


def sao_paulo(destino: Path, valor: str, inss="0,00", ir="0,00", csll="0,00", cofins="0,00", pis="0,00",
              codigo="07498", descricao="Manutenção preventiva de gerador"):
    """Parecido com a NFS-e da Prefeitura de São Paulo (código municipal + tabela de retenções)."""
    return _pdf(destino, [
        "PREFEITURA DO MUNICÍPIO DE SÃO PAULO",
        "NOTA FISCAL ELETRÔNICA DE SERVIÇOS - NFS-e",
        "Número da Nota 00000958",
        "DISCRIMINAÇÃO DOS SERVIÇOS",
        descricao,
        f"VALOR TOTAL DO SERVIÇO = R$ {valor}",
        [(40, "INSS (R$)"), (130, "IRRF (R$)"), (220, "CSLL (R$)"), (310, "COFINS (R$)"), (400, "PIS/PASEP (R$)")],
        [(40, inss), (130, ir), (220, csll), (310, cofins), (400, pis)],
        f"Código do Serviço: {codigo} - Manutenção e conservação de máquinas e equipamentos",
    ])


def municipal_sem_codigo(destino: Path, valor: str, descricao="Manutenção preventiva em câmara fria"):
    """Prefeitura que imprime só o texto do item da LC 116, sem o número."""
    return _pdf(destino, [
        "NOTA FISCAL DE SERVIÇOS ELETRÔNICA",
        "Serviço: " + DESC_1401[:90],
        f"Discriminação: {descricao}",
        f"Valor dos Serviços: R$ {valor}",
        "Retenção do INSS: R$ 0,00   IR: R$ 0,00   PIS: R$ 0,00   COFINS: R$ 0,00   CSLL: R$ 0,00",
    ])


def texto_livre(destino: Path, valor: str):
    """Recibo de prefeitura pequena, em texto corrido: as regras não acham nada, a IA entende."""
    return _pdf(destino, [
        "RECIBO PROVISÓRIO DE SERVIÇOS - PREFEITURA MUNICIPAL",
        "Recebemos a importância de R$ " + valor + " referente à manutenção corretiva no gerador",
        "da loja 310, serviço enquadrado no item 14.01 da lista anexa à Lei Complementar 116/2003.",
        "Não houve retenção de tributos federais nesta prestação.",
    ])


# ---------------------------------------------------------------- planilhas
def base_fiscal(destino: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    p = wb.active
    p.title = "Prestadores x REINF"
    p.append(["Cod SAP", "Forn SAP", "Ctg. Serv.", "Desc. Ctg. Serv.", "Padrão Tributação", "Impostos"])
    for linha in [
        [1001, "GERADORES EXEMPLO LTDA", 20, "Manutenção preventiva com cessão de mão de obra", "F", "PCC e INSS 11%"],
        [1001, "GERADORES EXEMPLO LTDA", 100, "Manutenção corretiva", "A", "Sem Imp. Fed."],
        [1001, "GERADORES EXEMPLO LTDA", 101, "Manutenção preventiva sem cessão de mão de obra", "X", "PCC"],
        [2002, "FRIO SERVIÇOS EXEMPLO ME", 100, "Manutenção corretiva", "A", "Sem Imp. Fed."],
        [2002, "FRIO SERVIÇOS EXEMPLO ME", 101, "Manutenção preventiva sem cessão de mão de obra", "A", "Sem Imp. Fed."],
        [3003, "OBRAS EXEMPLO LTDA", 3, "Construção - empreitada global", "A", "Sem Imp. Fed."],
        [3003, "OBRAS EXEMPLO LTDA", 4, "Construção civil - empreitada parcial", "V", "INSS 11%"],
    ]:
        p.append(linha)

    plus = wb.create_sheet("PLUs")
    plus.append(["|PLU|", "|Descrição|", "|SERV|", "|116|", "|Categoria|", "|Descrição Categoria|",
                 "Conta Contábil ", "Descrição CC"])
    for linha in [
        [900101, "SERV1401 MANUT CORRETIVA", "SERV1401", DESC_1401, 100, "Manutenção corretiva", 400100, "Manutenção - serviços"],
        [900102, "SERV1401 MANUT CORRETIVA TI", "SERV1401", DESC_1401, 100, "Manutenção corretiva", 400200, "Manutenção - hardware"],
        [900103, "SERV1401 PREV COM CESSAO", "SERV1401", DESC_1401, 20, "Manutenção preventiva com cessão de mão de obra", 400100, "Manutenção - serviços"],
        [900104, "SERV1401 PREV SEM CESSAO", "SERV1401", DESC_1401, 101, "Manutenção preventiva sem cessão de mão de obra", 400100, "Manutenção - serviços"],
        [900201, "SERV0702 EMPREITADA GLOBAL", "SERV0702", DESC_0702, 3, "Construção - empreitada global", 400100, "Manutenção - serviços"],
        [900202, "SERV0702 EMPREITADA PARCIAL", "SERV0702", DESC_0702, 4, "Construção civil - empreitada parcial", 400100, "Manutenção - serviços"],
    ]:
        plus.append(linha)
    wb.save(destino)
    return destino


OMS = [  # O.M, fornecedor, preço, ocorrência
    (5000001, "1001", 417.75, "1000001"),
    (5000002, "1001", 1000.00, "1000002"),
    (5000003, "1001", 1000.00, "1000003"),
    (5000004, "1001", 2000.00, "1000004"),
    (5000005, "2002", 850.00, "1000005"),
    (5000006, "1001", 640.00, "1000006"),
    (5000007, "3003", 12000.00, "1000007"),
    (5000008, "9999", 300.00, "1000008"),
]


def planilha_om(destino: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha1"
    ws.append(["O.M", "Fornecedor", "Componente", "Qtd.necessária", "Preço", "Requisitante", "TEXTO BREVE", "ocorrencia"])
    for om, forn, preco, ocor in OMS:
        ws.append([om, forn, None, 1, preco, "REQUISITANTE", f"REA ordem {om}", ocor])
    wb.save(destino)
    return destino


def gerar(pasta: Path = PASTA) -> None:
    notas = pasta / "notas"
    notas.mkdir(parents=True, exist_ok=True)
    base_fiscal(pasta / "base_fiscal_exemplo.xlsx")
    planilha_om(pasta / "planilha_om_exemplo.xlsx")
    nacional(notas / "1000001.pdf", "417,75")                                        # sem retenção -> corretiva
    nacional(notas / "1000002.pdf", "1.000,00", cp="110,00", pcc="46,50",
             descricao="Manutenção preventiva mensal em gerador")                    # PCC + INSS -> prev. com cessão
    sao_paulo(notas / "1000003.pdf", "1.000,00", csll="10,00", cofins="30,00", pis="6,50")  # PCC -> prev. sem cessão
    sao_paulo(notas / "1000004.pdf", "2.000,00", ir="30,00", csll="20,00", cofins="60,00",
              pis="13,00")                                                           # IR 1,5% -> crítica
    municipal_sem_codigo(notas / "1000005.pdf", "850,00")                            # desempate pelo texto
    texto_livre(notas / "1000006.pdf", "640,00")                                     # só a IA lê
    nacional(notas / "1000007.pdf", "12.000,00", cp="1.320,00", item="07.02.01", texto_item=DESC_0702,
             descricao="Reforma de piso da loja 215")                                # obra com INSS 11%
    # 1000008: fornecedor fora da base, sem PDF


if __name__ == "__main__":
    gerar()
    print(f"Exemplos gerados em {PASTA}")
