"""Testa o fluxo completo sem chamar nenhuma API externa.

A IA é substituída por provedores falsos, para conferir o que acontece
quando ela acerta, quando erra o formato e quando a chamada falha.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from extrator import extrair_nota
from extrator.exportar import salvar_excel
from extrator.leitor import ler_texto
from extrator.llm import ProvedorOffline, _json_da_resposta, criar_provedor

EXEMPLOS = Path(__file__).parent.parent / "exemplos"


class ProvedorFalso:
    nome = "falso"

    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro = resposta, erro

    def extrair(self, texto):
        if self.erro:
            raise self.erro
        return self.resposta


RESPOSTA_IA = {
    "fornecedor": "Luz & Cia Materiais Elétricos S.A.",
    "cnpj_fornecedor": "27551983000100",
    "numero_nota": "31577",
    "data_emissao": "2026-10-21",
    "data_vencimento": "2026-11-20",
    "valor_total": 3126.40,
    "itens": [
        {"descricao": "LAMPADA LED TUBULAR 18W", "quantidade": 80, "valor_total": 1032.00},
        {"descricao": "CABO FLEXIVEL 2,5MM", "quantidade": 6, "valor_total": 1139.40},
        {"descricao": "DISJUNTOR BIPOLAR 32A", "quantidade": 15, "valor_total": 951.00},
        {"descricao": "FITA ISOLANTE 20M", "quantidade": 1, "valor_total": 4.00},
    ],
}


def test_resposta_correta_da_ia_fica_ok():
    r = extrair_nota("qualquer texto", ProvedorFalso(RESPOSTA_IA), "nota.txt")
    assert r.status == "OK", r.motivos
    assert len(r.nota.itens) == 4


def test_falha_na_ia_cai_no_modo_offline():
    texto = ler_texto(EXEMPLOS / "nota_01_nfse_refrigeracao.txt")
    r = extrair_nota(texto, ProvedorFalso(erro=TimeoutError("sem rede")), "nota_01")
    assert r.provedor == "offline (fallback)"
    assert r.status == "REVISAR"  # mesmo extraindo certo, quem usou o plano B pede revisão
    assert r.nota.cnpj_fornecedor == "41.287.365/0001-26"


def test_resposta_fora_do_formato_vai_para_revisao():
    r = extrair_nota("texto", ProvedorFalso({"valor_total": "muito dinheiro"}), "x")
    assert r.status == "REVISAR"
    assert any("fora do formato" in m for m in r.motivos)


def test_json_com_cerca_markdown():
    assert _json_da_resposta('```json\n{"numero_nota": "1"}\n```') == {"numero_nota": "1"}


def test_offline_extrai_nfse_padrao():
    texto = ler_texto(EXEMPLOS / "nota_01_nfse_refrigeracao.txt")
    dados = ProvedorOffline().extrair(texto)
    assert dados["fornecedor"] == "FrioTec Refrigeração Comercial Ltda"
    assert dados["numero_nota"] == "4821"
    assert dados["data_emissao"] == "2026-10-14"
    assert dados["data_vencimento"] == "2026-11-13"
    assert dados["valor_total"] == 4890.00


def test_offline_numero_do_danfe_sem_pontos_e_zeros():
    texto = ler_texto(EXEMPLOS / "nota_02_danfe_eletrica.txt")
    assert ProvedorOffline().extrair(texto)["numero_nota"] == "31577"


def test_offline_detecta_cnpj_invalido():
    texto = ler_texto(EXEMPLOS / "nota_03_cnpj_invalido.txt")
    r = extrair_nota(texto, ProvedorOffline(), "nota_03")
    assert any("CNPJ" in m for m in r.motivos)


def test_le_pdf():
    assert "Hidra Soluções Hidráulicas" in ler_texto(EXEMPLOS / "nota_05_layout_diferente.pdf")


def test_sem_chave_usa_offline(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert criar_provedor("gemini").nome == "offline"


def test_planilha_tem_as_duas_abas(tmp_path):
    r = extrair_nota("x", ProvedorFalso(RESPOSTA_IA), "nota.txt")
    destino = salvar_excel([r], tmp_path / "saida.xlsx")
    from openpyxl import load_workbook

    planilha = load_workbook(destino)
    assert planilha.sheetnames == ["Notas", "Itens"]
    assert planilha["Itens"].max_row == 5


def test_api(monkeypatch):
    monkeypatch.setenv("LLM_PROVEDOR", "offline")
    import api

    cliente = TestClient(api.app)
    assert cliente.get("/saude").json()["status"] == "ok"

    texto = ler_texto(EXEMPLOS / "nota_01_nfse_refrigeracao.txt")
    resposta = cliente.post("/extrair", json={"texto": texto, "arquivo": "nota_01"})
    assert resposta.status_code == 200
    assert resposta.json()["nota"]["numero_nota"] == "4821"

    with open(EXEMPLOS / "nota_05_layout_diferente.pdf", "rb") as f:
        resposta = cliente.post("/extrair/arquivo", files={"arquivo": ("nota_05.pdf", f, "application/pdf")})
    assert resposta.status_code == 200

    assert cliente.post("/extrair", json={"texto": "   "}).status_code == 422
