"""A regra de escolha do PLU, do jeito que a legenda da base fiscal descreve:

1. Código de serviço da NFS-e -> SERV (14.01 -> SERV1401)
2. Tributação federal destacada na nota -> qual categoria liberada para o prestador vale
3. SERV + categoria -> PLU (na aba PLUs). Se houver mais de um, decide a conta contábil preferida
   ou o PLU que a equipe definiu no config.

Se em algum passo sobrar dúvida, a linha não é preenchida: fica marcada com o motivo e as opções.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .base_fiscal import BaseFiscal, CategoriaPrestador, Plu
from .leitor_pdf import DadosNota
from .tributacao import normalizar

PALAVRAS_IGNORADAS = {"servico", "servicos", "com", "sem", "de", "do", "da", "e", "mao", "obra", "cessao"}


@dataclass
class Escolha:
    status: str                          # OK / REVISAR
    plu: str | None = None
    motivo: str = ""
    categoria: CategoriaPrestador | None = None
    opcoes: list[str] = field(default_factory=list)


def _desempatar_por_texto(cats: list[CategoriaPrestador], texto: str) -> list[CategoriaPrestador]:
    """Ex.: nota fala em 'preventiva' -> fica a categoria de manutenção preventiva."""
    t = normalizar(texto)
    pontos = []
    for c in cats:
        palavras = {p for p in re.findall(r"[a-z]{5,}", normalizar(c.descricao)) if p not in PALAVRAS_IGNORADAS}
        pontos.append(sum(1 for p in palavras if p[:7] in t))
    melhor = max(pontos, default=0)
    if melhor == 0:
        return cats
    return [c for c, p in zip(cats, pontos) if p == melhor]


def _escolher_plu(candidatos: list[Plu], serv: str, cat: int, plu_preferido: dict[str, str],
                  contas_preferidas: list[str]) -> tuple[Plu | None, list[Plu]]:
    chave = f"{serv}|{cat}"
    if chave in plu_preferido:
        fixo = plu_preferido[chave]
        return Plu(fixo, "definido no config", serv, "", cat, "", "", ""), []
    if len(candidatos) == 1:
        return candidatos[0], []
    for conta in contas_preferidas:
        da_conta = [p for p in candidatos if p.conta == str(conta)]
        if len(da_conta) == 1:
            return da_conta[0], []
        if da_conta:
            return None, da_conta
    return None, candidatos


def escolher(base: BaseFiscal, fornecedor, nota: DadosNota | None, preco: Decimal | None,
             plu_preferido: dict[str, str] | None = None,
             contas_preferidas: list[str] | None = None) -> Escolha:
    plu_preferido = plu_preferido or {}
    contas_preferidas = [str(c) for c in (contas_preferidas or [])]

    cats = base.categorias(fornecedor)
    if not cats:
        return Escolha("REVISAR", motivo=f"Fornecedor {fornecedor} não está na base fiscal (aba Prestadores x REINF)")
    if nota is None:
        return Escolha("REVISAR", motivo="PDF da nota não encontrado")
    if not nota.serv:
        extra = f" (código municipal {nota.codigo_municipal}: inclua no de-para do config)" if nota.codigo_municipal else ""
        return Escolha("REVISAR", motivo=f"Código de serviço não encontrado no PDF{extra}")

    serv = nota.serv
    com_plu = [c for c in cats if base.plus_de(serv, c.categoria)]
    if not com_plu:
        liberadas = "; ".join(f"{c.categoria} {c.descricao}" for c in cats)
        return Escolha("REVISAR", motivo=f"Nenhum PLU {serv} para as categorias do prestador ({liberadas})")

    trib = nota.tributacao(preco)
    if trib is not None:
        mesma_trib = [c for c in com_plu if c.tributacao == trib]
        if not mesma_trib:
            liberadas = "; ".join(f"{c.descricao} = {c.impostos}" for c in com_plu)
            return Escolha("REVISAR", motivo=(f"Tributação da nota ({trib}) não bate com nenhum padrão liberado "
                                              f"para o prestador no {serv}: {liberadas}. Vai dar crítica no agendamento"))
        candidatas = mesma_trib
        como = f"{serv} + tributação da nota ({trib})"
    else:
        candidatas = com_plu
        como = f"{serv} (retenções não lidas no PDF)"

    if len(candidatas) > 1:
        candidatas = _desempatar_por_texto(candidatas, nota.texto)
    if len(candidatas) > 1:
        opcoes = [f"{c.categoria} {c.descricao} ({c.impostos})" for c in candidatas]
        return Escolha("REVISAR", motivo=f"{como}: mais de uma categoria possível", opcoes=opcoes)

    cat = candidatas[0]
    plu, empatados = _escolher_plu(base.plus_de(serv, cat.categoria), serv, cat.categoria,
                                   plu_preferido, contas_preferidas)
    if plu is None:
        opcoes = [f"{p.plu} {p.descricao} (conta {p.conta} {p.descricao_conta})" for p in empatados]
        return Escolha("REVISAR", categoria=cat, opcoes=opcoes,
                       motivo=f"{como} -> categoria {cat.categoria} {cat.descricao}: mais de um PLU; "
                              f"defina a conta preferida ou o PLU no config")
    return Escolha("OK", plu=plu.plu, categoria=cat,
                   motivo=f"{como} -> categoria {cat.categoria} {cat.descricao} -> PLU {plu.plu}")
