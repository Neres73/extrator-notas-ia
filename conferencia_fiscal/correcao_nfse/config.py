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

    # Onde estão os arquivos e o que fazer no fim (caminhos relativos partem da pasta do config.json).
    pasta_xml: Path | None = None
    parametros: Path | None = None
    fila: Path | None = None              # opcional: sem fila, confere todos os XMLs da pasta
    pasta_saida: Path = Path("saida")
    abrir_planilha: bool = True           # abre a planilha no Excel no fim (Windows)
    sap: str = "simular"                  # "nao", "simular" ou "lancar"

    @classmethod
    def carregar(cls, caminho: str | Path | None) -> "Config":
        cfg = cls()
        if not caminho:
            return cfg
        caminho = Path(caminho)
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as erro:
            raise ValueError(f"{caminho.name} tem um erro de digitação na linha {erro.lineno}: {erro.msg}. "
                             "Dica: em caminhos do Windows use barra normal (/) ou barra dupla (\\\\).") from erro

        pasta_config = caminho.resolve().parent

        def resolver(valor) -> Path | None:
            if not valor:
                return None
            p = Path(valor)
            return p if p.is_absolute() or str(valor).startswith("\\\\") else pasta_config / p

        entrada = dados.get("entrada", {})
        cfg.pasta_xml = resolver(entrada.get("pasta_xml"))
        cfg.parametros = resolver(entrada.get("parametros"))
        cfg.fila = resolver(entrada.get("fila"))
        saida = dados.get("saida", {})
        cfg.pasta_saida = resolver(saida.get("pasta")) or pasta_config / "saida"
        cfg.abrir_planilha = bool(saida.get("abrir_planilha", True))
        sap = str(dados.get("sap", "simular")).lower()
        if sap not in ("nao", "simular", "lancar"):
            raise ValueError(f'"sap" no {caminho.name} precisa ser "nao", "simular" ou "lancar" (veio "{sap}")')
        cfg.sap = sap
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
