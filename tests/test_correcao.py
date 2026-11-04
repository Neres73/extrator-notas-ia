"""Processo de correção, sem SAP e sem Excel: dados FICTÍCIOS e objetos falsos no lugar do SAP GUI."""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(RAIZ))

from correcao import Item, ligar_registros, lotes  # noqa: E402
from plu import base_geral, input_om, sap  # noqa: E402

D = Decimal


def _base(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Base"
    ws.append(["Ocorrência", "Doc.compras", "Fornecedor", "Razão Social", "CNPJ", "Status", "Vlr Total", "Cen.", "TIME"])
    ws.append([111, 4800000001, 1001, "A", "1", "Pendência - Impostos Federais", 900.5, "0608", "PCM"])
    ws.append([222, 4800000002, 1001, "A", "1", "Pendência - Impostos Federais", 15000, "0608", "PCM"])
    ws.append([333, 4800000003, 2002, "B", "2", "MIGO Pendente", 100, "1004", "PCM"])
    ws.append([444, 4800000004, 2002, "B", "2", "Pendência - Valor Divergente", 100, 977, "CAPEX"])
    ws.append([555, 4800000005, 3003, "C", "3", "Pendência - Código de Serviço Divergente", 10000, 977, "PCM"])
    arq = tmp_path / "base.xlsx"
    wb.save(arq)
    return arq


def test_base_geral_le_e_filtra(tmp_path):
    todas = base_geral.ler(_base(tmp_path))
    assert len(todas) == 5
    assert todas[0].ocorrencia == "111" and todas[0].pedido == "4800000001" and todas[0].fornecedor == "1001"
    assert todas[4].centro == "0977"                              # número vira texto com 4 dígitos
    filas = ["Impostos Federais", "Código de Serviço Divergente", "Valor Divergente"]
    ficam = base_geral.filtrar(todas, filas, "PCM", D("10000"))
    assert [o.ocorrencia for o in ficam] == ["111", "555"]       # 222 passa do limite, 333 fila, 444 time


def test_modelo_locais_e_capacidade(tmp_path):
    wb = Workbook()
    wb.active.title = "Input"
    wb["Input"].append(["Tipo de nota"])
    for i in range(2, 6):
        wb["Input"].append([f"=IF('Criar OM Massa'!A{i}=\"\",\"\",'Criar OM Massa'!A{i})"])
    loc = wb.create_sheet("Base Locais")
    loc.append(["Centro custo", "Cen.localiz.", "Loc.instalação", "Denominação"])
    loc.append(["0001", "0001", "GPA-BR-SP-PA-P1-0001", "0001 - LOJA"])
    loc.append([608, 608, "GPA-BR-SP-XX-0608", "0608 - LOJA"])
    wb.create_sheet("Criar OM Massa")
    arq = tmp_path / "modelo.xlsx"
    wb.save(arq)
    locais, capacidade = input_om.ler_modelo(arq)
    assert capacidade == 4
    assert locais == {"0001": "GPA-BR-SP-PA-P1-0001", "0608": "GPA-BR-SP-XX-0608"}


def test_linha_da_planilha_de_criacao():
    linha = input_om.montar_linha("REA ordem46321315", "2329", "GPA-LOCAL", {"Tipo de nota": "Z6"}, date(2026, 11, 4))
    assert linha == {"Tipo de nota": "Z6", "Texto breve": "REA ordem46321315", "Centro de custo": "2329",
                     "Local de instalação": "GPA-LOCAL", "Data base início": "04.11.2026"}
    assert input_om.chave("Grupo de codes – codificação") == input_om.chave("Grupo de codes - codificação")


# ---------------------------------------------------------------- relatório da transação (SAP falso)
class Rotulo:
    def __init__(self, x, y, texto):
        self.Id, self.Text = f"/app/con[0]/ses[0]/wnd[0]/usr/lbl[{x},{y}]", texto


class Colecao(list):
    @property
    def Count(self):
        return len(self)

    def ElementAt(self, i):
        return self[i]


class Usr:
    def __init__(self, rotulos):
        self.Children = Colecao(rotulos)


def test_le_relatorio_em_lista_classica():
    usr = Usr([
        Rotulo(1, 1, "Relatório dos Registros"),
        Rotulo(1, 3, "Registro"), Rotulo(10, 3, "Sucesso / Erro"), Rotulo(25, 3, "Num. Ordem"),
        Rotulo(36, 3, "Num. Nota"), Rotulo(45, 3, "Descrição"),
        Rotulo(8, 4, "1"), Rotulo(25, 4, "46502251"), Rotulo(36, 4, "5113171"), Rotulo(45, 4, "Registro criado com sucesso"),
        Rotulo(8, 5, "2"), Rotulo(45, 5, "Erro: centro de custo bloqueado"),
    ])
    regs = sap.registros_do_relatorio(sap.ler_lista(usr))
    assert [(r.registro, r.ordem, r.nota, r.ok) for r in regs] == [(1, "46502251", "5113171", True), (2, "", "", False)]


class Grid:
    Type, SubType, VisibleRowCount = "GuiShell", "GridView", 2

    def __init__(self, titulos, linhas):
        self.ColumnOrder = Colecao(list(titulos))
        self._titulos, self._linhas = titulos, linhas
        self.RowCount = len(linhas)
        self.firstVisibleRow = 0

    def GetDisplayedColumnTitle(self, nome):
        return self._titulos[nome]

    def GetCellValue(self, i, nome):
        return self._linhas[i][nome]


def test_le_relatorio_em_grid():
    grid = Grid({"REG": "Registro", "AUFNR": "Num. Ordem", "QMNUM": "Num. Nota", "TXT": "Descrição"}, [
        {"REG": "1", "AUFNR": "46502251", "QMNUM": "5113171", "TXT": "Registro criado com sucesso"},
        {"REG": "2", "AUFNR": "46502252", "QMNUM": "5113172", "TXT": "Registro criado com sucesso"},
        {"REG": "3", "AUFNR": "46502253", "QMNUM": "5113173", "TXT": "Registro criado com sucesso"},
    ])
    regs = sap.registros_do_relatorio(sap.ler_grid(grid))
    assert [r.ordem for r in regs if r.ok] == ["46502251", "46502252", "46502253"]


def _item(oc):
    return Item(base_geral.Ocorrencia(1, oc, "48", "1001", D("10"), "x", "0001", "PCM"))


def test_liga_om_nova_pela_ordem_das_linhas():
    lote = [_item("a"), _item("b"), _item("c")]
    regs = [sap.Registro(1, "46502251", "5113171", "Registro criado com sucesso"),
            sap.Registro(2, "", "", "Centro bloqueado")]
    ligar_registros(lote, regs)
    assert lote[0].om_nova == "46502251" and lote[0].status == "PENDENTE"
    assert lote[1].status == "ERRO" and "Centro bloqueado" in lote[1].motivo
    assert lote[2].status == "ERRO" and "não apareceu" in lote[2].motivo


def test_lotes_respeitam_a_capacidade_da_planilha():
    assert [len(l) for l in lotes(list(range(300)), 138)] == [138, 138, 24]


def test_historico_impede_criar_om_duas_vezes(tmp_path):
    from correcao import gravar_historico, ler_historico
    arq = tmp_path / "historico.csv"
    assert ler_historico(arq) == {}
    it = _item("123")
    it.om_nova, it.ordem_original, it.plu = "46502251", "46321315", "900101"
    gravar_historico(arq, [it])
    gravar_historico(arq, [])                                    # segunda gravação não repete o cabeçalho
    assert ler_historico(arq)["123"].startswith("OM 46502251 em ")


# ---------------------------------------------------------------- tela do NIX (cockpit)
def _tela_nix():
    from plu.nix import Elemento
    e = lambda x, y, t, tipo="GuiTextField": Elemento(f"id{x}_{y}", tipo, t, x, y, 21)  # noqa: E731
    lbl = lambda x, y, t: e(x, y, t, "GuiLabel")  # noqa: E731
    return [
        lbl(40, 405, "Serviço LC:"), e(312, 405, "14.01"), e(390, 405, "LUBRIFICACAO, LIMPEZA, LUSTRACAO"),
        lbl(66, 644, "Valor Total:"), e(272, 644, "440,00"), e(650, 644, "0,00"),
        lbl(66, 678, "Valor Líquido:"), e(272, 678, "440,00"), e(650, 678, "0,00"),
        lbl(66, 780, "ISSQN:"), e(272, 780, "13,20"), e(650, 780, "0,00"),
        lbl(66, 814, "PIS:"), e(272, 814, "6,60"), e(650, 814, "0,00"),
        lbl(66, 848, "COFINS:"), e(272, 848, "30,40"), e(650, 848, "0,00"),
        lbl(66, 882, "CSLL:"), e(272, 882, "4,40"), e(650, 882, "0,00"),
        lbl(66, 916, "IRRF:"), e(272, 916, "6,60"), e(650, 916, "0,00"),
        lbl(66, 950, "INSS:"), e(272, 950, "0,00"), e(650, 950, "0,00"),
    ]


def test_le_codigo_e_impostos_da_tela_do_nix():
    from plu.nix import ler_campos, nota_da_tela
    from plu.tributacao import Tributacao
    nota = nota_da_tela("105217996", ler_campos(_tela_nix()))
    assert nota.item_lc116 == "14.01" and nota.serv == "SERV1401"
    assert nota.valor_servicos == D("440.00")
    assert (nota.ir, nota.pcc, nota.inss) == (D("6.60"), D("41.40"), D("0.00"))
    assert nota.tributacao() == Tributacao(ir=D("1.5"), pcc=True)


def test_nota_sem_retencao_na_tela_do_nix():
    from plu.nix import Elemento, ler_campos, nota_da_tela
    from plu.tributacao import Tributacao
    els = [Elemento(x.id, x.tipo, "0,00" if x.x == 272 and x.y >= 814 else x.texto, x.x, x.y, x.altura)
           for x in _tela_nix()]
    nota = nota_da_tela("1", ler_campos(els))
    assert nota.tributacao() == Tributacao()
