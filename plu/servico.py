"""O caminho de uma nota, igual para a planilha (escolher_plu.py) e para a API (api.py):

PDF -> leitura por regras -> (IA, se faltou algo) -> de-para municipal -> regra fiscal -> PLU
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .base_fiscal import BaseFiscal, carregar
from .escolha import Escolha, escolher
from .leitor_ia import Provedor, completar_com_ia, criar_provedor
from .leitor_pdf import DadosNota, ler_nota


@dataclass
class Configuracao:
    base: BaseFiscal
    provedor_ia: Provedor | None = None
    codigos_municipais: dict[str, str] = field(default_factory=dict)
    plu_preferido: dict[str, str] = field(default_factory=dict)
    contas_preferidas: list[str] = field(default_factory=list)
    categorias_preferidas: list[int] = field(default_factory=list)


def carregar_json(caminho: Path) -> dict:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise ValueError(f"{caminho.name} com erro na linha {erro.lineno}: {erro.msg}. "
                         "Em caminhos do Windows use / ou \\\\.") from erro


def resolver(pasta: Path, valor: str | None) -> Path | None:
    if not valor:
        return None
    p = Path(valor)
    return p if p.is_absolute() or str(valor).startswith(("\\\\", "//")) else pasta / p


def montar(cfg: dict, pasta: Path) -> Configuracao:
    base_arq = resolver(pasta, cfg.get("base_fiscal"))
    if not base_arq or not base_arq.is_file():
        raise ValueError(f"Base fiscal não encontrada: {base_arq or '(preencha base_fiscal no config)'}")
    ia = cfg.get("ia", {})
    return Configuracao(
        base=carregar(base_arq),
        provedor_ia=criar_provedor(ia.get("provedor"), ia.get("modelo")),
        codigos_municipais={re.sub(r"\D", "", k).lstrip("0"): v for k, v in cfg.get("codigos_municipais", {}).items()},
        plu_preferido=cfg.get("plu_preferido", {}),
        contas_preferidas=[str(c) for c in cfg.get("contas_preferidas", [])],
        categorias_preferidas=[int(c) for c in cfg.get("categorias_preferidas", [])],
    )


def analisar(pdf: Path | None, fornecedor, preco: Decimal | None, conf: Configuracao,
             texto: str | None = None) -> tuple[Escolha, DadosNota | None]:
    nota = None
    if pdf is not None:
        try:
            nota = ler_nota(pdf, conf.base.servs(), texto=texto)
        except Exception as erro:  # noqa: BLE001 - PDF corrompido não pode parar o lote
            return Escolha("REVISAR", motivo=f"PDF ilegível: {erro}"), None
        nota = completar_com_ia(nota, conf.provedor_ia)
        if not nota.item_lc116 and nota.codigo_municipal:
            nota.item_lc116 = conf.codigos_municipais.get(nota.codigo_municipal.lstrip("0"))
    escolha = escolher(conf.base, fornecedor, nota, preco,
                       plu_preferido=conf.plu_preferido, contas_preferidas=conf.contas_preferidas,
                       categorias_preferidas=conf.categorias_preferidas)
    return escolha, nota
