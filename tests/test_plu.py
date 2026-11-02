"""Testes com dados FICTÍCIOS (base fiscal, planilha e PDFs gerados aqui)."""

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "exemplos"))

from plu import base_fiscal, planilha_om  # noqa: E402
from plu.escolha import escolher  # noqa: E402
from plu.leitor_pdf import DadosNota, achar_codigo, ler_nota  # noqa: E402
from plu.tributacao import Tributacao  # noqa: E402

D = Decimal
DESC_1401 = ("Lubrificação, limpeza, lustração, revisão, carga e recarga, conserto, restauração, blindagem, "
             "manutenção e conservação de máquinas, veículos, aparelhos, equipamentos, motores, elevadores")


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def base(tmp_path):
    wb = Workbook()
    p = wb.active
    p.title = "Prestadores x REINF"
    p.append(["Cod SAP", "Forn SAP", "Ctg. Serv.", "Desc. Ctg. Serv.", "Padrão Tributação", "Impostos"])
    p.append([1001, "GERADORES EXEMPLO LTDA", 20, "Manutenção preventiva com cessão de mão de obra", "F", "PCC e INSS 11%"])
    p.append([1001, "GERADORES EXEMPLO LTDA", 100, "Manutenção corretiva", "A", "Sem Imp. Fed."])
    p.append([1001, "GERADORES EXEMPLO LTDA", 101, "Manutenção preventiva sem cessão de mão de obra", "X", "PCC"])
    p.append([2002, "MULTI SERVIÇOS ME", 100, "Manutenção corretiva", "A", "Sem Imp. Fed."])
    p.append([2002, "MULTI SERVIÇOS ME", 101, "Manutenção preventiva sem cessão de mão de obra", "A", "Sem Imp. Fed."])
    p.append([3003, "OBRAS EXEMPLO LTDA", 3, "Construção - empreitada global", "A", "Sem Imp. Fed."])
    plus = wb.create_sheet("PLUs")
    plus.append(["|PLU|", "|Descrição|", "|SERV|", "|116|", "|Categoria|", "|Descrição Categoria|",
                 "Conta Contábil ", "Descrição CC"])
    plus.append([900001, "SERV1401 CORRETIVA A", "SERV1401", DESC_1401, 100, "Manutenção corretiva", 400100, "Contratos"])
    plus.append([900002, "SERV1401 CORRETIVA B", "SERV1401", DESC_1401, 100, "Manutenção corretiva", 400200, "Serviços"])
    plus.append([900003, "SERV1401 PREV COM CESSAO", "SERV1401", DESC_1401, 20, "Manutenção preventiva com cessão", 400100, "Contratos"])
    plus.append([900004, "SERV1401 PREV SEM CESSAO", "SERV1401", DESC_1401, 101, "Manutenção preventiva sem cessão", 400100, "Contratos"])
    plus.append([900005, "SERV0702 OBRA", "SERV0702", "Execução, por administração, empreitada...", 3, "Construção", 400200, "Serviços"])
    arquivo = tmp_path / "base.xlsx"
    wb.save(arquivo)
    return base_fiscal.carregar(arquivo)


def nota(item="14.01", ir=None, pcc=None, inss=None, valor="1000", texto="") -> DadosNota:
    return DadosNota("nota.pdf", texto, item_lc116=item, valor_servicos=D(valor),
                     ir=None if ir is None else D(ir), pcc=None if pcc is None else D(pcc),
                     inss=None if inss is None else D(inss))


# ---------------------------------------------------------------- tributação
@pytest.mark.parametrize("texto, esperado", [
    ("Sem Imp. Fed.", Tributacao()),
    ("IR 1,5% e PCC", Tributacao(ir=D("1.5"), pcc=True)),
    ("IR 1% e PCC ", Tributacao(ir=D("1"), pcc=True)),
    ("PCC e INSS 11%", Tributacao(pcc=True, inss=D("11"))),
    ("IR 1%, PCC e INSS 11%", Tributacao(ir=D("1"), pcc=True, inss=D("11"))),
    ("INSS 3,5%", Tributacao(inss=D("3.5"))),
    ("IR 1,5%", Tributacao(ir=D("1.5"))),
    ("PCC", Tributacao(pcc=True)),
    ("IR 1,5%, PIS, COFINS e INSS 3,5%", Tributacao(ir=D("1.5"), pcc=True, inss=D("3.5"))),
    ("IR 1,5%, COFINS, CS e INSS 3,5%", Tributacao(ir=D("1.5"), pcc=True, inss=D("3.5"))),
    ("Pessoa Física", Tributacao(pessoa_fisica=True)),
])
def test_tributacao_da_base(texto, esperado):
    assert Tributacao.do_texto(texto) == esperado


def test_tributacao_pelos_valores_da_nota():
    assert Tributacao.dos_valores(D("2000"), D("30"), D("93"), D("0")) == Tributacao(ir=D("1.5"), pcc=True)
    assert Tributacao.dos_valores(D("1000"), D("0"), D("46.5"), D("110")) == Tributacao(pcc=True, inss=D("11"))
    assert Tributacao.dos_valores(D("1000"), D("0"), D("0"), D("0")) == Tributacao()


# ---------------------------------------------------------------- base fiscal
def test_base_le_prestadores_e_plus(base):
    assert len(base.categorias(1001)) == 3
    assert len(base.categorias("1001")) == 3
    assert len(base.categorias(1001.0)) == 3
    assert base.categorias(9999) == []
    assert {p.plu for p in base.plus_de("SERV1401", 100)} == {"900001", "900002"}


# ---------------------------------------------------------------- escolha
def test_tributacao_da_nota_define_a_categoria(base):
    e = escolher(base, 1001, nota(ir="0", pcc="46.50", inss="110"), None)
    assert (e.status, e.plu) == ("OK", "900003")
    e = escolher(base, 1001, nota(ir="0", pcc="46.50", inss="0"), None)
    assert (e.status, e.plu) == ("OK", "900004")


def test_varios_plus_na_categoria_usa_a_conta_preferida(base):
    e = escolher(base, 1001, nota(ir="0", pcc="0", inss="0"), None)
    assert e.status == "REVISAR" and len(e.opcoes) == 2
    e = escolher(base, 1001, nota(ir="0", pcc="0", inss="0"), None, contas_preferidas=["400200"])
    assert (e.status, e.plu) == ("OK", "900002")


def test_plu_definido_no_config_tem_prioridade(base):
    e = escolher(base, 1001, nota(ir="0", pcc="0", inss="0"), None, plu_preferido={"SERV1401|100": "9009999"})
    assert (e.status, e.plu) == ("OK", "9009999")


def test_tributacao_que_nao_bate_avisa_critica(base):
    e = escolher(base, 1001, nota(ir="15", pcc="46.5", inss="0"), None)
    assert e.status == "REVISAR"
    assert "crítica no agendamento" in e.motivo


def test_mesma_tributacao_desempata_pelo_texto_da_nota(base):
    sem_texto = escolher(base, 2002, nota(ir="0", pcc="0", inss="0"), None)
    assert sem_texto.status == "REVISAR" and "mais de uma categoria" in sem_texto.motivo
    e = escolher(base, 2002, nota(ir="0", pcc="0", inss="0", texto="Manutenção preventiva mensal"), None,
                 contas_preferidas=["400100"])
    assert (e.status, e.plu) == ("OK", "900004")


def test_sem_retencoes_lidas_mas_so_uma_categoria_possivel(base):
    e = escolher(base, 3003, nota(item="07.02"), None)
    assert (e.status, e.plu) == ("OK", "900005")


def test_usa_preco_da_planilha_quando_nota_sem_valor(base):
    n = nota(ir="0", pcc="46.50", inss="110", valor="0")
    n.valor_servicos = None
    assert escolher(base, 1001, n, D("1000")).plu == "900003"


@pytest.mark.parametrize("fornecedor, n, trecho", [
    (9999, nota(), "não está na base fiscal"),
    (1001, None, "PDF da nota não encontrado"),
    (1001, nota(item=None), "Código de serviço não encontrado"),
    (1001, nota(item="17.01"), "Nenhum PLU SERV1701"),
])
def test_casos_que_vao_para_revisao(base, fornecedor, n, trecho):
    e = escolher(base, fornecedor, n, None)
    assert e.status == "REVISAR" and trecho in e.motivo


# ---------------------------------------------------------------- leitura do código de serviço
@pytest.mark.parametrize("texto, item, municipal", [
    ("Código de Tributação Nacional: 14.01.01 - Lubrificação", "14.01", None),
    ("Item da Lista de Serviços: 7.02", "07.02", None),
    ("Código do Serviço: 1401 - Manutenção", "14.01", None),
    ("Código do Serviço: 07498 - Manutenção", None, "07498"),
    ("Código da Atividade: 3314-7/10", None, None),          # CNAE não é confundido com LC 116
])
def test_achar_codigo(texto, item, municipal):
    achado, mun, _ = achar_codigo(texto, {})
    assert (achado, mun) == (item, municipal)


def test_codigo_pela_descricao_da_lc116(base):
    item, _, como = achar_codigo("Serviço: " + DESC_1401[:80], base.servs())
    assert item == "14.01" and "descrição" in como


# ---------------------------------------------------------------- leitura de PDF (layouts simulados)
@pytest.fixture
def g():
    pytest.importorskip("reportlab")
    import gerar_exemplos
    return gerar_exemplos


def test_pdf_nacional_tabela_em_colunas(g, tmp_path, base):
    n = ler_nota(g.nacional(tmp_path / "n.pdf", "1.000,00", cp="110,00", pcc="46,50"), base.servs())
    assert n.item_lc116 == "14.01"
    assert (n.valor_servicos, n.ir, n.pcc, n.inss) == (D("1000.00"), D("0.00"), D("46.50"), D("110.00"))
    assert n.tributacao() == Tributacao(pcc=True, inss=D("11"))


def test_pdf_sao_paulo(g, tmp_path, base):
    n = ler_nota(g.sao_paulo(tmp_path / "sp.pdf", "2.000,00", ir="30,00", csll="20,00", cofins="60,00", pis="13,00"),
                 base.servs())
    assert (n.item_lc116, n.codigo_municipal) == (None, "07498")
    assert n.tributacao() == Tributacao(ir=D("1.5"), pcc=True)


def test_pdf_so_com_descricao(g, tmp_path, base):
    n = ler_nota(g.municipal_sem_codigo(tmp_path / "m.pdf", "189,25"), base.servs())
    assert n.item_lc116 == "14.01"
    assert n.tributacao() == Tributacao()


# ---------------------------------------------------------------- planilha das OMs
def test_planilha_preenche_componente_e_marca_revisar(base, tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["O.M", "Fornecedor", "Componente", "Qtd.necessária", "Preço", "Requisitante", "TEXTO BREVE", "ocorrencia"])
    ws.append([1, "1001", 9009999, 1, 1000.0, "REQ", "REA ordem 1", "111"])
    ws.append([2, "1001", 9009999, 1, 500.0, "REQ", "REA ordem 2", "222"])
    origem = tmp_path / "om.xlsx"
    wb.save(origem)

    linhas = planilha_om.ler(origem)
    assert [l.ocorrencia for l in linhas] == ["111", "222"]
    resultados = [(linhas[0], escolher(base, linhas[0].fornecedor, nota(ir="0", pcc="46.5", inss="110"), linhas[0].preco)),
                  (linhas[1], escolher(base, linhas[1].fornecedor, None, linhas[1].preco))]
    destino = planilha_om.salvar(origem, tmp_path / "saida" / "om_plu.xlsx", resultados)

    ws = load_workbook(destino).active
    assert ws["C2"].value == 900003 and ws["I2"].value == "OK" and "antes: 9009999" in ws["J2"].value
    assert ws["C3"].value is None and ws["I3"].value == "REVISAR"
    assert load_workbook(origem).active["C2"].value == 9009999        # original intacto


def test_fornecedor_fora_da_base_lista_os_plus_do_servico(base):
    e = escolher(base, 9999, nota(), None)
    assert e.status == "REVISAR" and "padrão de tributação" in e.motivo
    assert len(e.opcoes) == 4 and all("SERV1401" in o for o in e.opcoes)
