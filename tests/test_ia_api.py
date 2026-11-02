"""IA de reserva (com provedor falso, sem chamar API paga), API e execução de ponta a ponta com os exemplos."""

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(RAIZ))

from plu.leitor_ia import completar_com_ia, precisa_da_ia  # noqa: E402
from plu.leitor_pdf import DadosNota  # noqa: E402
from plu.servico import analisar, carregar_json, montar  # noqa: E402

EXEMPLOS = RAIZ / "exemplos"
D = Decimal


class IAFalsa:
    nome = "falsa"

    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro, self.chamadas = resposta, erro, 0

    def responder(self, texto):
        self.chamadas += 1
        if self.erro:
            raise self.erro
        return self.resposta if isinstance(self.resposta, str) else json.dumps(self.resposta)


LEITURA_OK = {"item_lc116": "14.01", "valor_servicos": 640.0, "irrf": 0, "pis": 0, "cofins": 0, "csll": 0, "inss": 0}


@pytest.fixture(scope="module")
def conf():
    return montar(carregar_json(RAIZ / "config.exemplo.json"), RAIZ)


# ---------------------------------------------------------------- IA de reserva
def test_ia_nao_e_chamada_quando_as_regras_bastam():
    nota = DadosNota("n.pdf", "texto", item_lc116="14.01", ir=D("0"), pcc=D("0"), inss=D("0"))
    ia = IAFalsa(LEITURA_OK)
    completar_com_ia(nota, ia)
    assert ia.chamadas == 0 and not precisa_da_ia(nota)


def test_ia_completa_so_o_que_faltou():
    nota = DadosNota("n.pdf", "recibo em texto livre", valor_servicos=D("640"))
    completar_com_ia(nota, IAFalsa(LEITURA_OK))
    assert nota.item_lc116 == "14.01"
    assert (nota.ir, nota.pcc, nota.inss) == (D("0"), D("0"), D("0"))
    assert nota.lido_pela_ia == ["código de serviço", "retenções"]


def test_ia_nao_sobrescreve_o_que_as_regras_leram():
    nota = DadosNota("n.pdf", "texto", item_lc116="07.02")
    completar_com_ia(nota, IAFalsa(LEITURA_OK))
    assert nota.item_lc116 == "07.02" and nota.lido_pela_ia == ["retenções"]


@pytest.mark.parametrize("resposta, erro", [
    ("desculpe, não consegui ler", None),                         # não é JSON
    ({**LEITURA_OK, "item_lc116": "3314-7/10"}, None),            # CNAE no lugar da LC 116
    ({**LEITURA_OK, "irrf": -15}, None),                          # valor negativo
    (None, TimeoutError("sem internet")),                          # API fora do ar
])
def test_resposta_ruim_da_ia_vira_aviso_e_nao_inventa_nada(resposta, erro):
    nota = DadosNota("n.pdf", "texto livre")
    completar_com_ia(nota, IAFalsa(resposta, erro))
    assert nota.item_lc116 is None and not nota.leu_retencoes
    assert nota.avisos and "IA (falsa)" in nota.avisos[0]


def test_ia_resolve_a_nota_em_texto_livre(conf):
    pdf = EXEMPLOS / "notas" / "1000006.pdf"
    sem_ia, _ = analisar(pdf, "1001", D("640"), conf)
    assert sem_ia.status == "REVISAR"

    conf.provedor_ia = IAFalsa(LEITURA_OK)
    try:
        com_ia, nota = analisar(pdf, "1001", D("640"), conf)
    finally:
        conf.provedor_ia = None
    assert (com_ia.status, com_ia.plu) == ("OK", "900101")
    assert "lido pela IA" in com_ia.motivo


# ---------------------------------------------------------------- ponta a ponta com os exemplos
ESPERADO = {
    "1000001": ("OK", 900101), "1000002": ("OK", 900103), "1000003": ("OK", 900104),
    "1000004": ("REVISAR", None), "1000005": ("OK", 900104), "1000006": ("REVISAR", None),
    "1000007": ("OK", 900202), "1000008": ("REVISAR", None),
}


def test_executar_com_os_exemplos(tmp_path, monkeypatch, capsys):
    import escolher_plu

    cfg = carregar_json(RAIZ / "config.exemplo.json")
    cfg.update({"pasta_saida": str(tmp_path), "abrir_planilha": False})
    monkeypatch.setattr(escolher_plu, "carregar_json", lambda _: cfg)
    assert escolher_plu.main() == 0
    assert "5 OM(s) com PLU preenchido" in capsys.readouterr().out

    [saida] = tmp_path.glob("*.xlsx")
    ws = load_workbook(saida).active
    obtido = {str(r[7]): (r[8], r[2]) for r in ws.iter_rows(min_row=2, values_only=True)}
    assert obtido == ESPERADO


# ---------------------------------------------------------------- API
@pytest.fixture(scope="module")
def cliente():
    from fastapi.testclient import TestClient

    import api
    return TestClient(api.app)


def test_api_saude(cliente):
    assert cliente.get("/saude").json()["status"] == "ok"


def test_api_sugere_plu(cliente):
    with open(EXEMPLOS / "notas" / "1000002.pdf", "rb") as f:
        r = cliente.post("/sugerir-plu", files={"nota": ("nota.pdf", f, "application/pdf")},
                         data={"fornecedor": "1001"})
    corpo = r.json()
    assert r.status_code == 200
    assert (corpo["status"], corpo["plu"]) == ("OK", "900103")
    assert corpo["nota"]["tributacao"] == "PCC e INSS 11%"
    assert corpo["fornecedor"] == "GERADORES EXEMPLO LTDA"


def test_api_explica_quando_nao_da(cliente):
    with open(EXEMPLOS / "notas" / "1000004.pdf", "rb") as f:
        corpo = cliente.post("/sugerir-plu", files={"nota": ("nota.pdf", f, "application/pdf")},
                             data={"fornecedor": "1001", "preco": "2.000,00"}).json()
    assert corpo["status"] == "REVISAR" and "crítica" in corpo["motivo"]


def test_api_recusa_arquivo_que_nao_e_pdf(cliente):
    r = cliente.post("/sugerir-plu", files={"nota": ("nota.txt", b"x", "text/plain")}, data={"fornecedor": "1001"})
    assert r.status_code == 415
