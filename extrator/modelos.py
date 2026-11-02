"""Esquema dos dados extraídos de uma nota fiscal e regras de validação.

A IA sugere os campos; quem decide se o resultado é confiável são as regras daqui.
Qualquer regra que falhar manda a nota para revisão humana, em vez de aceitá-la em silêncio.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer, field_validator

# Valores em Decimal (sem erro de arredondamento) que saem como número no JSON da API.
Dinheiro = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


def somente_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def cnpj_valido(cnpj: str) -> bool:
    """Confere os dois dígitos verificadores do CNPJ."""
    numeros = somente_digitos(cnpj)
    if len(numeros) != 14 or numeros == numeros[0] * 14:
        return False

    def digito(base: str, pesos: list[int]) -> str:
        resto = sum(int(n) * p for n, p in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    d1 = digito(numeros[:12], pesos1)
    d2 = digito(numeros[:12] + d1, pesos2)
    return numeros[-2:] == d1 + d2


def formatar_cnpj(cnpj: str) -> str:
    n = somente_digitos(cnpj)
    if len(n) != 14:
        return cnpj
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


class ItemNota(BaseModel):
    descricao: str
    quantidade: Dinheiro = Field(default=Decimal("1"))
    valor_total: Dinheiro


class NotaFiscal(BaseModel):
    fornecedor: str | None = None
    cnpj_fornecedor: str | None = None
    numero_nota: str | None = None
    data_emissao: date | None = None
    data_vencimento: date | None = None
    valor_total: Dinheiro | None = None
    itens: list[ItemNota] = Field(default_factory=list)

    @field_validator("cnpj_fornecedor")
    @classmethod
    def _normaliza_cnpj(cls, v: str | None) -> str | None:
        return formatar_cnpj(v) if v else v


class ResultadoExtracao(BaseModel):
    arquivo: str
    status: str  # "OK" ou "REVISAR"
    motivos: list[str] = Field(default_factory=list)
    provedor: str
    nota: NotaFiscal


CAMPOS_OBRIGATORIOS = ["fornecedor", "cnpj_fornecedor", "numero_nota", "data_emissao", "valor_total"]

# Diferença máxima aceita entre o total da nota e a soma dos itens (arredondamentos).
TOLERANCIA_TOTAL = Decimal("0.05")


def validar(nota: NotaFiscal) -> list[str]:
    """Devolve a lista de problemas encontrados. Lista vazia significa nota OK."""
    problemas: list[str] = []

    for campo in CAMPOS_OBRIGATORIOS:
        if getattr(nota, campo) in (None, ""):
            problemas.append(f"Campo obrigatório ausente: {campo}")

    if nota.cnpj_fornecedor and not cnpj_valido(nota.cnpj_fornecedor):
        problemas.append(f"CNPJ com dígito verificador inválido: {nota.cnpj_fornecedor}")

    if nota.valor_total is not None and nota.valor_total <= 0:
        problemas.append("Valor total precisa ser maior que zero")

    if nota.itens and nota.valor_total is not None:
        soma = sum((i.valor_total for i in nota.itens), Decimal("0"))
        if abs(soma - nota.valor_total) > TOLERANCIA_TOTAL:
            problemas.append(
                f"Soma dos itens (R$ {soma:.2f}) diferente do total da nota (R$ {nota.valor_total:.2f})"
            )

    if nota.data_emissao and nota.data_vencimento and nota.data_vencimento < nota.data_emissao:
        problemas.append("Vencimento anterior à data de emissão")

    if nota.data_emissao and nota.data_emissao > date.today():
        problemas.append("Data de emissão no futuro")

    return problemas
