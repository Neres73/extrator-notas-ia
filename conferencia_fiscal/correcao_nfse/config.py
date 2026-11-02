"""Configuração: nomes das colunas das planilhas e limites das regras.

Os nomes de coluna abaixo são os que a macro procura primeiro. Se a sua planilha usar outro nome,
basta trocar no config.json (não precisa mexer no código). A procura ignora maiúsculas, acentos e espaços.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

# Para cada campo lógico, a lista de nomes de coluna aceitos (o primeiro que existir na planilha é usado).
COLUNAS_PARAMETROS = {
    "item_lc116": ["Código Serviço", "Cod Servico", "Item LC 116", "Item Lista Serviço", "Código LC 116", "Cód. Serviço"],
    "codigo_municipal": ["Código Municipal", "Cod Municipal", "Código Prefeitura", "Código SP"],
    "descricao": ["Descrição", "Descricao", "Descrição Serviço"],
    "plu": ["PLU", "Código PLU", "Material"],
    "irrf": ["IRRF %", "IRRF", "Alíquota IRRF", "IR %"],
    "pcc": ["PCC %", "PIS/COFINS/CSLL %", "CSRF %", "PCC"],
    "inss": ["INSS %", "INSS", "Alíquota INSS"],
    "retem_iss": ["Retém ISS", "Retem ISS", "ISS Retido", "Retenção ISS"],
}

COLUNAS_FILA = {
    "numero_nota": ["Nº Nota", "Nota", "Número NF", "NF", "Nota Fiscal", "Nº NF"],
    "cnpj_prestador": ["CNPJ", "CNPJ Fornecedor", "CNPJ Prestador"],
    "ocorrencia": ["Ocorrência", "Ocorrencia"],
    "pedido": ["Pedido", "Nº Pedido", "Pedido SAP"],
    "plu_atual": ["PLU", "PLU Atual", "Material"],
    "arquivo_xml": ["Arquivo XML", "XML", "Caminho XML"],
}


@dataclass
class Config:
    colunas_parametros: dict[str, list[str]] = field(default_factory=lambda: dict(COLUNAS_PARAMETROS))
    colunas_fila: dict[str, list[str]] = field(default_factory=lambda: dict(COLUNAS_FILA))
    aba_parametros: str | None = None          # None = primeira aba
    aba_fila: str | None = None

    # Raiz do CNPJ da empresa tomadora (8 primeiros dígitos). Nota para outro tomador vai para revisão.
    cnpj_raiz_tomador: str | None = None
    # Diferença aceita entre o imposto esperado e o da nota (arredondamento).
    tolerancia: Decimal = Decimal("0.05")
    # Retenção esperada abaixo deste valor é considerada dispensada (vira zero).
    valor_minimo_retencao: Decimal = Decimal("10.00")

    @classmethod
    def carregar(cls, caminho: str | Path | None) -> "Config":
        cfg = cls()
        if not caminho:
            return cfg
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        for chave in ("colunas_parametros", "colunas_fila"):
            for campo, nomes in dados.get(chave, {}).items():
                atual = getattr(cfg, chave)
                atual[campo] = list(nomes) + [n for n in atual.get(campo, []) if n not in nomes]
        for chave in ("aba_parametros", "aba_fila", "cnpj_raiz_tomador"):
            if chave in dados:
                setattr(cfg, chave, dados[chave])
        for chave in ("tolerancia", "valor_minimo_retencao"):
            if chave in dados:
                setattr(cfg, chave, Decimal(str(dados[chave])))
        return cfg
