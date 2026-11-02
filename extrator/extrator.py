"""Orquestra o fluxo: texto da nota -> modelo de IA -> validação -> resultado."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from .llm import Provedor, ProvedorOffline
from .modelos import NotaFiscal, ResultadoExtracao, validar

log = logging.getLogger(__name__)


def extrair_nota(texto: str, provedor: Provedor, arquivo: str = "texto") -> ResultadoExtracao:
    motivos: list[str] = []
    usado = provedor.nome

    try:
        dados = provedor.extrair(texto)
    except Exception as erro:  # rede fora, cota estourada, JSON malformado...
        log.warning("%s: falha no provedor %s (%s). Usando modo offline.", arquivo, provedor.nome, erro)
        motivos.append(f"Falha na IA ({provedor.nome}), extraído pelo modo offline")
        usado = "offline (fallback)"
        dados = ProvedorOffline().extrair(texto)

    try:
        nota = NotaFiscal.model_validate(dados)
    except ValidationError as erro:
        campos = ", ".join(str(e["loc"][0]) for e in erro.errors())
        log.warning("%s: resposta fora do formato esperado (%s)", arquivo, campos)
        motivos.append(f"Resposta fora do formato esperado nos campos: {campos}")
        nota = NotaFiscal()

    motivos.extend(validar(nota))
    status = "OK" if not motivos else "REVISAR"
    log.info("%s: %s via %s", arquivo, status, usado)

    return ResultadoExtracao(arquivo=arquivo, status=status, motivos=motivos, provedor=usado, nota=nota)
