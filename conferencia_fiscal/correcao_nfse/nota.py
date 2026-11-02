"""Modelo único de nota de serviço, igual para todos os layouts de XML."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .utils import ZERO


@dataclass
class NotaServico:
    arquivo: str
    layout: str                              # "nacional", "abrasf" ou "sao_paulo"

    numero: str | None = None
    chave: str | None = None                 # chave de acesso (nacional) ou código de verificação
    data_emissao: date | None = None
    competencia: date | None = None
    cancelada: bool = False

    cnpj_prestador: str | None = None
    nome_prestador: str | None = None
    cnpj_tomador: str | None = None
    nome_tomador: str | None = None

    item_lc116: str | None = None            # "14.01"
    codigo_tributacao_nacional: str | None = None   # "140101" (layout nacional)
    codigo_municipal: str | None = None      # código da prefeitura (ex.: São Paulo usa 5 dígitos)
    descricao_servico: str | None = None

    valor_servicos: Decimal = ZERO
    base_calculo: Decimal = ZERO
    aliquota_iss: Decimal = ZERO             # em %
    valor_iss: Decimal = ZERO
    iss_retido: bool = False

    irrf_retido: Decimal = ZERO
    pcc_retido: Decimal = ZERO               # PIS + COFINS + CSLL retidos, somados
    inss_retido: Decimal = ZERO
    valor_liquido: Decimal = ZERO

    avisos: list[str] = field(default_factory=list)   # observações da leitura (não são erros)

    @property
    def identificacao(self) -> str:
        return f"NFS-e {self.numero or '?'} / {self.nome_prestador or self.cnpj_prestador or 'prestador ?'}"
