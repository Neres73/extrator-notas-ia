"""IA como leitora de RESERVA: só entra quando a leitura por regras não achou o que precisa no PDF.

A IA só lê. Ela devolve um JSON com o código de serviço e as retenções, esse JSON é validado,
e quem escolhe o PLU continua sendo a regra fiscal (plu/escolha.py). Assim, um erro da IA
nunca vira PLU errado em silêncio: no pior caso a nota vai para revisão.

Provedores: "gemini" (chave gratuita no Google AI Studio), "claude" ou "nenhum" (padrão).
Com "nenhum", nenhum dado sai da máquina.
"""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from .leitor_pdf import DadosNota

PROMPT = """Você lê o texto de uma NFS-e (nota fiscal de serviço brasileira) e extrai só estes campos.
Responda APENAS com um objeto JSON, sem texto antes ou depois:

{
  "item_lc116": "código do serviço na Lista da LC 116 no formato NN.NN (ex.: 14.01), ou null",
  "codigo_municipal": "código de serviço da prefeitura, se a nota só trouxer esse, ou null",
  "valor_servicos": 0.00,
  "irrf": 0.00,
  "pis": 0.00,
  "cofins": 0.00,
  "csll": 0.00,
  "inss": 0.00
}

Regras:
- Os impostos são os valores RETIDOS destacados na nota. Se a nota mostra 0,00 ou não mostra, use 0.
- Valores com ponto decimal (1.234,56 vira 1234.56).
- O código da LC 116 tem 2 dígitos, ponto e 2 dígitos. Não confunda com o CNAE (ex.: 3314-7/10).
- Se um campo não aparecer, use null. Nunca invente.
"""


class LeituraIA(BaseModel):
    item_lc116: str | None = None
    codigo_municipal: str | None = None
    valor_servicos: Decimal | None = Field(default=None, ge=0)
    irrf: Decimal = Field(default=Decimal("0"), ge=0)
    pis: Decimal = Field(default=Decimal("0"), ge=0)
    cofins: Decimal = Field(default=Decimal("0"), ge=0)
    csll: Decimal = Field(default=Decimal("0"), ge=0)
    inss: Decimal = Field(default=Decimal("0"), ge=0)

    @field_validator("irrf", "pis", "cofins", "csll", "inss", mode="before")
    @classmethod
    def _nulo_vira_zero(cls, v):
        return 0 if v is None else v

    @field_validator("item_lc116")
    @classmethod
    def _formato_lc116(cls, v):
        if v is None:
            return None
        m = re.fullmatch(r"(\d{1,2})[.,](\d{2})(?:[.,]\d{2})?", str(v).strip())
        if not m or not 1 <= int(m.group(1)) <= 40:
            raise ValueError(f"código LC 116 inválido: {v}")
        return f"{int(m.group(1)):02d}.{m.group(2)}"


class Provedor(Protocol):
    nome: str

    def responder(self, texto: str) -> str: ...


class Gemini:
    nome = "gemini"

    def __init__(self, chave: str, modelo: str | None = None):
        from google import genai

        self._cliente = genai.Client(api_key=chave)
        self._modelo = modelo or "gemini-flash-latest"

    def responder(self, texto: str) -> str:
        from google.genai import types

        r = self._cliente.models.generate_content(
            model=self._modelo, contents=texto,
            config=types.GenerateContentConfig(system_instruction=PROMPT, temperature=0,
                                               response_mime_type="application/json"))
        return r.text


class Claude:
    nome = "claude"

    def __init__(self, chave: str, modelo: str | None = None):
        import anthropic

        self._cliente = anthropic.Anthropic(api_key=chave)
        self._modelo = modelo or "claude-haiku-5-5"

    def responder(self, texto: str) -> str:
        r = self._cliente.messages.create(model=self._modelo, max_tokens=800, system=PROMPT,
                                          messages=[{"role": "user", "content": texto}])
        return "".join(b.text for b in r.content if b.type == "text")


def criar_provedor(nome: str | None, modelo: str | None = None) -> Provedor | None:
    nome = (nome or "nenhum").lower()
    if nome == "gemini" and os.getenv("GEMINI_API_KEY"):
        return Gemini(os.environ["GEMINI_API_KEY"], modelo)
    if nome == "claude" and os.getenv("ANTHROPIC_API_KEY"):
        return Claude(os.environ["ANTHROPIC_API_KEY"], modelo)
    return None


def _json(resposta: str) -> dict:
    bloco = re.search(r"\{.*\}", resposta or "", re.DOTALL)
    if not bloco:
        raise ValueError("a IA não devolveu JSON")
    return json.loads(bloco.group(0))


def precisa_da_ia(nota: DadosNota) -> bool:
    return bool(nota.texto.strip()) and (not nota.item_lc116 or not nota.leu_retencoes)


def completar_com_ia(nota: DadosNota, provedor: Provedor | None) -> DadosNota:
    """Preenche só o que a leitura por regras não achou. Nunca sobrescreve o que já foi lido."""
    if provedor is None or not precisa_da_ia(nota):
        return nota
    try:
        lido = LeituraIA.model_validate(_json(provedor.responder(nota.texto[:12000])))
    except (ValueError, ValidationError) as erro:
        nota.avisos.append(f"IA ({provedor.nome}) não ajudou: {str(erro)[:120]}")
        return nota
    except Exception as erro:  # noqa: BLE001 - rede fora, cota, chave inválida: segue sem a IA
        nota.avisos.append(f"IA ({provedor.nome}) indisponível: {str(erro)[:120]}")
        return nota

    if not nota.item_lc116 and lido.item_lc116:
        nota.item_lc116 = lido.item_lc116
        nota.origem_codigo = f"IA ({provedor.nome})"
        nota.lido_pela_ia.append("código de serviço")
    if not nota.item_lc116 and not nota.codigo_municipal and lido.codigo_municipal:
        nota.codigo_municipal = re.sub(r"\D", "", lido.codigo_municipal) or None
    if not nota.leu_retencoes:
        nota.ir, nota.inss = lido.irrf, lido.inss
        nota.pcc = lido.pis + lido.cofins + lido.csll
        nota.lido_pela_ia.append("retenções")
        if nota.valor_servicos is None:
            nota.valor_servicos = lido.valor_servicos
    return nota
