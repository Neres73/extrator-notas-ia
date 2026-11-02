"""Provedores que transformam o texto da nota em um dicionário de campos.

- gemini:  Google Gemini (chave gratuita no Google AI Studio)
- claude:  Anthropic Claude
- offline: expressões regulares, sem IA. Serve de plano B quando não há chave
           ou quando a chamada ao modelo falha, e é usado nos testes.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

PROMPT_SISTEMA = """Você extrai dados de notas fiscais brasileiras (NF-e, NFS-e, DANFE).
Responda APENAS com um objeto JSON, sem texto antes ou depois, neste formato:

{
  "fornecedor": "razão social do emitente/prestador",
  "cnpj_fornecedor": "CNPJ do emitente/prestador, só dígitos",
  "numero_nota": "número da nota",
  "data_emissao": "AAAA-MM-DD",
  "data_vencimento": "AAAA-MM-DD ou null",
  "valor_total": 1234.56,
  "itens": [{"descricao": "...", "quantidade": 1, "valor_total": 1234.56}]
}

Regras:
- O fornecedor é quem EMITE a nota, nunca o tomador/destinatário.
- Valores em número com ponto decimal (1.234,56 vira 1234.56).
- Se um campo não aparecer no texto, use null. Nunca invente valores.
"""


class Provedor(Protocol):
    nome: str

    def extrair(self, texto: str) -> dict: ...


def _json_da_resposta(resposta: str) -> dict:
    """Aceita a resposta com ou sem cerca ```json``` em volta."""
    limpo = resposta.strip()
    bloco = re.search(r"\{.*\}", limpo, re.DOTALL)
    if not bloco:
        raise ValueError(f"O modelo não devolveu JSON: {limpo[:200]}")
    return json.loads(bloco.group(0))


class ProvedorGemini:
    nome = "gemini"

    def __init__(self, api_key: str, modelo: str | None = None):
        from google import genai

        self._cliente = genai.Client(api_key=api_key)
        self._modelo = modelo or os.getenv("LLM_MODELO") or "gemini-flash-latest"

    def extrair(self, texto: str) -> dict:
        from google.genai import types

        resposta = self._cliente.models.generate_content(
            model=self._modelo,
            contents=texto,
            config=types.GenerateContentConfig(
                system_instruction=PROMPT_SISTEMA,
                response_mime_type="application/json",
                temperature=0,
            ),
        )
        return _json_da_resposta(resposta.text)


class ProvedorClaude:
    nome = "claude"

    def __init__(self, api_key: str, modelo: str | None = None):
        import anthropic

        self._cliente = anthropic.Anthropic(api_key=api_key)
        self._modelo = modelo or os.getenv("LLM_MODELO") or "claude-haiku-5-5"

    def extrair(self, texto: str) -> dict:
        resposta = self._cliente.messages.create(
            model=self._modelo,
            max_tokens=2000,
            system=PROMPT_SISTEMA,
            messages=[{"role": "user", "content": texto}],
        )
        conteudo = "".join(b.text for b in resposta.content if b.type == "text")
        return _json_da_resposta(conteudo)


class ProvedorOffline:
    """Extração por regex para layouts comuns. Menos flexível que a IA, mas não depende de rede."""

    nome = "offline"

    _CNPJ = r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}"
    _DATA = r"(\d{2})/(\d{2})/(\d{4})"
    _VALOR = r"R?\$?\s*([\d.]+,\d{2})"

    def extrair(self, texto: str) -> dict:
        return {
            "fornecedor": self._fornecedor(texto),
            "cnpj_fornecedor": self._primeiro(rf"CNPJ[^\d]{{0,15}}({self._CNPJ})", texto),
            "numero_nota": self._numero(texto),
            "data_emissao": self._data(r"Emiss[ãa]o", texto),
            "data_vencimento": self._data(r"Vencimento", texto),
            "valor_total": self._valor(r"(?:Valor Total(?: da Nota| dos Servi[çc]os)?|TOTAL)", texto),
            "itens": [],
        }

    @staticmethod
    def _primeiro(padrao: str, texto: str) -> str | None:
        m = re.search(padrao, texto, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _numero(self, texto: str) -> str | None:
        """'Nº 000.031.577' -> '31577'"""
        bruto = self._primeiro(r"(?:N[ºo°]\.?|N[úu]mero(?: da [Nn]ota)?)\s*:?\s*(\d[\d.]*)", texto)
        if not bruto:
            return None
        return bruto.replace(".", "").lstrip("0") or "0"

    def _fornecedor(self, texto: str) -> str | None:
        padrao = r"(?:Prestador|Emitente|Raz[ãa]o Social)[^:\n]*:\s*(.+)"
        return self._primeiro(padrao, texto)

    def _data(self, rotulo: str, texto: str) -> str | None:
        m = re.search(rf"{rotulo}[^\d\n]{{0,25}}{self._DATA}", texto, re.IGNORECASE)
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None

    def _valor(self, rotulo: str, texto: str) -> float | None:
        m = re.search(rf"{rotulo}[^\d\n]{{0,20}}{self._VALOR}", texto, re.IGNORECASE)
        if not m:
            return None
        return float(m.group(1).replace(".", "").replace(",", "."))


def criar_provedor(nome: str | None = None) -> Provedor:
    """Escolhe o provedor pelo argumento ou pela variável LLM_PROVEDOR.

    Sem chave configurada, cai no modo offline em vez de quebrar.
    """
    nome = (nome or os.getenv("LLM_PROVEDOR") or "gemini").lower()

    if nome == "gemini" and os.getenv("GEMINI_API_KEY"):
        return ProvedorGemini(os.environ["GEMINI_API_KEY"])
    if nome == "claude" and os.getenv("ANTHROPIC_API_KEY"):
        return ProvedorClaude(os.environ["ANTHROPIC_API_KEY"])
    return ProvedorOffline()
