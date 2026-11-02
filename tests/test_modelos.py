from datetime import date
from decimal import Decimal

import pytest

from extrator.modelos import NotaFiscal, cnpj_valido, validar


@pytest.mark.parametrize("cnpj", ["41.287.365/0001-26", "41287365000126", "27.551.983/0001-00"])
def test_cnpj_valido(cnpj):
    assert cnpj_valido(cnpj)


@pytest.mark.parametrize("cnpj", ["63.840.217/0001-21", "11.111.111/1111-11", "123", ""])
def test_cnpj_invalido(cnpj):
    assert not cnpj_valido(cnpj)


def nota_ok(**alteracoes) -> NotaFiscal:
    dados = {
        "fornecedor": "FrioTec Refrigeração Comercial Ltda",
        "cnpj_fornecedor": "41287365000126",
        "numero_nota": "4821",
        "data_emissao": "2026-10-14",
        "data_vencimento": "2026-11-13",
        "valor_total": 4890.00,
        "itens": [
            {"descricao": "Manutenção corretiva", "valor_total": 1850},
            {"descricao": "Troca de compressor", "valor_total": 2400},
            {"descricao": "Recarga de gás", "valor_total": 640},
        ],
    }
    dados.update(alteracoes)
    return NotaFiscal.model_validate(dados)


def test_nota_valida_nao_tem_problemas():
    assert validar(nota_ok()) == []


def test_cnpj_e_formatado():
    assert nota_ok().cnpj_fornecedor == "41.287.365/0001-26"


def test_soma_dos_itens_divergente():
    problemas = validar(nota_ok(valor_total=5000))
    assert any("Soma dos itens" in p for p in problemas)


def test_diferenca_de_arredondamento_e_tolerada():
    assert validar(nota_ok(valor_total=4890.03)) == []


def test_vencimento_antes_da_emissao():
    problemas = validar(nota_ok(data_vencimento="2026-09-01"))
    assert "Vencimento anterior à data de emissão" in problemas


def test_campo_obrigatorio_ausente():
    problemas = validar(nota_ok(fornecedor=None, numero_nota=None))
    assert "Campo obrigatório ausente: fornecedor" in problemas
    assert "Campo obrigatório ausente: numero_nota" in problemas


def test_emissao_no_futuro():
    futuro = date(date.today().year + 1, 1, 1).isoformat()
    assert "Data de emissão no futuro" in validar(nota_ok(data_emissao=futuro, data_vencimento=None))


def test_valor_zero():
    problemas = validar(nota_ok(valor_total=0, itens=[]))
    assert "Valor total precisa ser maior que zero" in problemas


def test_decimal_preserva_centavos():
    assert nota_ok().valor_total == Decimal("4890.0")
