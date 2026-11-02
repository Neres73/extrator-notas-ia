"""Funções de apoio: leitura de XML, números, CNPJ e códigos de serviço.

`xml_sem_ns` foi reaproveitada da macro gerar_pedido (leitura de XML da NF-e).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")


def xml_sem_ns(conteudo: str | bytes) -> ET.Element:
    """Lê o XML e tira os namespaces dos nomes (assim 'infNFSe', 'Servico'... funcionam direto).

    Aceita texto ou bytes; com bytes respeita a codificação declarada no arquivo.
    Também escapa "&" soltos, que alguns sistemas deixam no texto e quebram a leitura.
    """
    if isinstance(conteudo, str):
        texto = conteudo.lstrip("﻿").strip()
        texto = re.sub(r"^<\?xml[^>]*\?>", "", texto)
        dados = texto.encode("utf-8")
    else:
        dados = conteudo.lstrip(b"\xef\xbb\xbf").strip()
    dados = re.sub(rb"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", b"&amp;", dados)
    raiz = ET.fromstring(dados)
    for el in raiz.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
        if ":" in str(el.tag):
            el.tag = el.tag.split(":", 1)[1]
    return raiz


def achar(el: ET.Element | None, *caminhos: str) -> ET.Element | None:
    """Primeiro elemento encontrado entre os caminhos (busca em qualquer profundidade)."""
    if el is None:
        return None
    for caminho in caminhos:
        achado = el.find(caminho if caminho.startswith(".") else f".//{caminho}")
        if achado is not None:
            return achado
    return None


def texto(el: ET.Element | None, *caminhos: str) -> str | None:
    achado = achar(el, *caminhos)
    if achado is None or achado.text is None:
        return None
    valor = achado.text.strip()
    return valor or None


def decimal(valor: str | None) -> Decimal:
    """'1234.56' (XML) ou '1.234,56' -> Decimal. Vazio vira zero."""
    if not valor:
        return ZERO
    v = valor.strip()
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return Decimal(v)
    except InvalidOperation:
        return ZERO


def numero(el: ET.Element | None, *caminhos: str) -> Decimal:
    return decimal(texto(el, *caminhos))


def data(valor: str | None) -> date | None:
    """Aceita '2026-10-14', '2026-10-14T09:32:11-03:00' ou '14/10/2026'."""
    if not valor:
        return None
    v = valor.strip()
    for formato, tamanho in (("%Y-%m-%d", 10), ("%d/%m/%Y", 10), ("%Y%m%d", 8)):
        try:
            return datetime.strptime(v[:tamanho], formato).date()
        except ValueError:
            continue
    return None


def so_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def cnpj_valido(cnpj: str | None) -> bool:
    n = so_digitos(cnpj)
    if len(n) != 14 or n == n[0] * 14:
        return False

    def dv(base: str, pesos: list[int]) -> str:
        resto = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(n[:12], p1)
    return n[-2:] == d1 + dv(n[:12] + d1, [6] + p1)


def item_lc116(valor: str | None) -> str | None:
    """Normaliza o código de serviço para o formato da LC 116: '14.01'.

    Aceita '14.01', '1401', '14.1', '140101' (código de tributação nacional, que traz o
    desdobramento nos 2 últimos dígitos) e '1401' vindo como número.
    """
    if not valor:
        return None
    v = valor.strip()
    m = re.fullmatch(r"(\d{1,2})[.,](\d{1,2})(?:[.,]\d{1,2})?", v)
    if m:
        return f"{int(m.group(1)):02d}.{int(m.group(2)):02d}"
    d = so_digitos(v)
    if len(d) == 6:          # código de tributação nacional: item + subitem + desdobramento
        return f"{d[:2]}.{d[2:4]}"
    if len(d) in (3, 4):     # '701' ou '1401'
        d = d.zfill(4)
        return f"{d[:2]}.{d[2:]}"
    return None


def moeda(valor: Decimal | None) -> str:
    if valor is None:
        return "-"
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
