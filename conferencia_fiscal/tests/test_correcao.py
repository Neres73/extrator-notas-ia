import sys
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).parent.parent))

from correcao_nfse.config import Config  # noqa: E402
from correcao_nfse.leitor_nfse import XmlInvalido, ler_arquivo, ler_xml  # noqa: E402
from correcao_nfse.planilhas import BaseParametros, carregar_fila, chave_nota  # noqa: E402
from correcao_nfse.processamento import processar  # noqa: E402
from correcao_nfse.regras import conferir, retencao_esperada  # noqa: E402
from correcao_nfse.relatorio import salvar  # noqa: E402
from correcao_nfse.utils import item_lc116  # noqa: E402

EX = Path(__file__).parent.parent / "exemplos"
XML = EX / "xml"


@pytest.fixture
def config():
    return Config()


@pytest.fixture
def base(config):
    return BaseParametros.carregar(EX / "parametros_fiscais_exemplo.xlsx", config)


# ---------------------------------------------------------------- leitura dos layouts
def test_nacional():
    [n] = ler_arquivo(XML / "01_nacional_ok.xml")
    assert n.layout == "nacional"
    assert n.numero == "4821"
    assert n.cnpj_prestador == "41287365000126"
    assert n.cnpj_tomador == "80451639000122"
    assert n.item_lc116 == "14.01"
    assert n.codigo_tributacao_nacional == "140101"
    assert n.valor_servicos == Decimal("10000.00")
    assert n.iss_retido and n.valor_iss == Decimal("500.00")
    assert n.irrf_retido == Decimal("100.00")
    assert n.pcc_retido == Decimal("465.00")
    assert n.valor_liquido == Decimal("8935.00")
    assert str(n.data_emissao) == "2026-10-14"


def test_abrasf_2():
    [n] = ler_arquivo(XML / "03_abrasf_ok.xml")
    assert n.layout == "abrasf"
    assert n.item_lc116 == "07.10"
    assert n.cnpj_prestador == "55027194000100"
    assert n.pcc_retido == Decimal("93.00")
    assert n.inss_retido == Decimal("220.00")
    assert not n.iss_retido


def test_abrasf_1_cancelada_em_iso_8859_1():
    [n] = ler_arquivo(XML / "04_abrasf_cancelada.xml")
    assert n.cancelada
    assert n.item_lc116 == "07.02"
    assert n.nome_prestador == "Luz & Cia Instalações Elétricas S.A."
    assert n.aliquota_iss == Decimal("3.00")        # veio como fração 0.03


def test_sao_paulo():
    [n] = ler_arquivo(XML / "05_sao_paulo_sem_pcc.xml")
    assert n.layout == "sao_paulo"
    assert n.numero == "958"
    assert n.codigo_municipal == "7498"
    assert n.item_lc116 is None
    assert n.aliquota_iss == Decimal("5.00")
    assert n.irrf_retido == Decimal("32.00")


def test_nfe_de_produto_e_recusada_com_motivo():
    with pytest.raises(XmlInvalido, match="NF-e de produtos"):
        ler_arquivo(XML / "07_nfe_de_produto.xml")


def test_html_salvo_como_xml():
    with pytest.raises(XmlInvalido, match="página da internet"):
        ler_xml(b"<!DOCTYPE html><html><body>erro</body></html>")


def test_xml_cortado():
    with pytest.raises(XmlInvalido, match="estrutura quebrada"):
        ler_xml(b"<CompNfse><Nfse><InfNfse><Numero>1</Numero>")


@pytest.mark.parametrize("entrada, saida", [
    ("14.01", "14.01"), ("1401", "14.01"), ("140101", "14.01"), ("7.02", "07.02"),
    ("0702", "07.02"), ("702", "07.02"), ("14.01.01", "14.01"), ("", None), ("abc", None),
])
def test_item_lc116(entrada, saida):
    assert item_lc116(entrada) == saida


# ---------------------------------------------------------------- planilhas
def test_base_acha_cabecalho_fora_da_primeira_linha(base):
    assert len(base.parametros) == 4
    assert base.buscar("14.01", None)[0].plu == "900101"
    assert base.buscar(None, "07498")[0].plu == "900204"        # código municipal com zero à esquerda
    assert base.buscar(None, "7498")[0].plu == "900204"


def test_fila_cnpj_numerico_perde_zero_mas_liga(config):
    fila = carregar_fila(EX / "fila_nfse_exemplo.xlsx", config)
    assert fila[1].chave == chave_nota("19.364.852/0001-96", "1207")
    assert chave_nota("01234567000189", "0001") == chave_nota("1234567000189", "1")


def test_config_aceita_nomes_de_coluna_diferentes(tmp_path):
    cfg_arquivo = tmp_path / "config.json"
    cfg_arquivo.write_text('{"colunas_parametros": {"plu": ["Cod Material SAP"]}, "tolerancia": 0.10}', "utf-8")
    cfg = Config.carregar(cfg_arquivo)
    assert cfg.colunas_parametros["plu"][0] == "Cod Material SAP"
    assert "PLU" in cfg.colunas_parametros["plu"]
    assert cfg.tolerancia == Decimal("0.10")


def test_coluna_obrigatoria_ausente_explica(tmp_path, config):
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["Código", "Descrição"])
    wb.save(tmp_path / "ruim.xlsx")
    with pytest.raises(ValueError, match="config.json"):
        BaseParametros.carregar(tmp_path / "ruim.xlsx", config)


# ---------------------------------------------------------------- regras
def test_retencao_abaixo_do_minimo_e_dispensada(config):
    assert retencao_esperada(Decimal("500"), Decimal("1"), config) == Decimal("0")       # R$ 5,00
    assert retencao_esperada(Decimal("2000"), Decimal("1"), config) == Decimal("20.00")


def test_nota_correta_fica_ok(base, config):
    [n] = ler_arquivo(XML / "01_nacional_ok.xml")
    r = conferir(n, base.buscar(n.item_lc116, n.codigo_municipal), config)
    assert r.status == "OK", r.motivos


def test_irrf_faltando_gera_correcao(base, config):
    [n] = ler_arquivo(XML / "02_nacional_sem_irrf.xml")
    r = conferir(n, base.buscar(n.item_lc116, n.codigo_municipal), config)
    assert r.status == "CORRIGIR"
    assert r.esperado["IRRF"] == Decimal("40.00")


def test_tomador_de_outra_empresa_vai_para_revisao(base):
    cfg = Config(cnpj_raiz_tomador="11111111")
    [n] = ler_arquivo(XML / "01_nacional_ok.xml")
    r = conferir(n, base.buscar(n.item_lc116, None), cfg)
    assert r.status == "REVISAR"
    assert "Tomador" in r.motivos[0]


def test_codigo_com_dois_plus_nao_escolhe_sozinho(base, config):
    [n] = ler_arquivo(XML / "01_nacional_ok.xml")
    p = base.buscar("14.01", None)[0]
    from dataclasses import replace
    r = conferir(n, [p, replace(p, plu="999999")], config)
    assert r.status == "REVISAR"
    assert "mais de um PLU" in r.motivos[0]


# ---------------------------------------------------------------- ponta a ponta
def test_lote_com_fila(base, config, tmp_path):
    fila = carregar_fila(EX / "fila_nfse_exemplo.xlsx", config)
    lote = processar(XML, base, config, fila)
    status = {(r.nota.numero if r.nota else r.fila.numero_nota): r.status for r in lote.resultados}
    assert status == {"4821": "OK", "1207": "CORRIGIR", "30412": "CORRIGIR", "958": "CORRIGIR", "777": "REVISAR"}
    assert lote.arquivos_invalidos[0][0] == "07_nfe_de_produto.xml"

    destino = salvar(lote, tmp_path / "saida.xlsx")
    wb = load_workbook(destino)
    assert wb.sheetnames == ["Pedidos de correção", "Revisar", "Conferência"]
    assert wb["Pedidos de correção"].max_row == 4          # cabeçalho + 3 pedidos
    assert wb["Revisar"].max_row == 3                      # cabeçalho + nota sem XML + XML inválido


def test_sap_em_simulacao_nao_conecta(base, config, capsys):
    from correcao_nfse.sap import lancar
    lote = processar(XML, base, config)
    retornos = lancar(lote.resultados, simulacao=True)
    assert len(retornos) == 2 and all(r.mensagem == "simulação" for r in retornos)
    assert "nada foi enviado ao SAP" in capsys.readouterr().out
