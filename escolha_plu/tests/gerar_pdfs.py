"""Gera PDFs de NFS-e FICTÍCIOS em layouts parecidos com os reais, para testar a leitura."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DESC_1401 = ("Lubrificação, limpeza, lustração, revisão, carga e recarga, conserto, restauração, blindagem, "
             "manutenção e conservação de máquinas, veículos, aparelhos, equipamentos, motores, elevadores")


def _pdf(destino: Path, linhas: list[str | tuple[float, str]]) -> Path:
    c = canvas.Canvas(str(destino), pagesize=A4)
    y = 800
    for item in linhas:
        if isinstance(item, tuple):          # várias colunas na mesma linha
            for x, txt in item[1]:
                c.drawString(x, y, txt)
        else:
            c.drawString(40, y, item)
        y -= 16
    c.save()
    return destino


def nacional(destino: Path, valor: str, irrf="0,00", cp="0,00", pcc="0,00", descricao="Manutenção corretiva gerador"):
    """Parecido com o DANFSe do padrão nacional."""
    return _pdf(destino, [
        "DANFSe v1.0 - Documento Auxiliar da NFS-e",
        "Número da NFS-e: 1207   Data e Hora da emissão: 20/10/2026 10:00",
        "EMITENTE DA NFS-e  CNPJ: 19.364.852/0001-96",
        "SERVIÇO PRESTADO",
        "Código de Tributação Nacional: 14.01.01 - " + DESC_1401[:60],
        f"Descrição do Serviço: {descricao}",
        "TRIBUTAÇÃO FEDERAL",
        (0, [(40, "IRRF"), (160, "Contribuição Previdenciária - Retida"), (380, "Contribuições Sociais - Retidas")]),
        (0, [(40, irrf), (160, cp), (380, pcc)]),
        f"Valor do Serviço: R$ {valor}",
    ])


def sao_paulo(destino: Path, valor: str, inss="0,00", ir="0,00", csll="0,00", cofins="0,00", pis="0,00",
              codigo="07498", descricao="Manutenção preventiva de gerador"):
    """Parecido com a NFS-e da Prefeitura de São Paulo (tabela de retenções)."""
    return _pdf(destino, [
        "PREFEITURA DO MUNICÍPIO DE SÃO PAULO",
        "NOTA FISCAL ELETRÔNICA DE SERVIÇOS - NFS-e",
        "Número da Nota 00000958",
        "DISCRIMINAÇÃO DOS SERVIÇOS",
        descricao,
        f"VALOR TOTAL DO SERVIÇO = R$ {valor}",
        (0, [(40, "INSS (R$)"), (130, "IRRF (R$)"), (220, "CSLL (R$)"), (310, "COFINS (R$)"), (400, "PIS/PASEP (R$)")]),
        (0, [(40, inss), (130, ir), (220, csll), (310, cofins), (400, pis)]),
        f"Código do Serviço: {codigo} - Manutenção e conservação de máquinas e equipamentos",
    ])


def municipal_sem_rotulo(destino: Path, valor: str):
    """Prefeitura que só imprime o texto do item da LC 116, sem o número."""
    return _pdf(destino, [
        "NOTA FISCAL DE SERVIÇOS ELETRÔNICA",
        "Serviço: " + DESC_1401[:90],
        f"Valor dos Serviços: R$ {valor}",
        "Retenção do INSS: R$ 0,00   IR: R$ 0,00   PIS: R$ 0,00   COFINS: R$ 0,00   CSLL: R$ 0,00",
    ])
