"""Leitura de XML de NFS-e nos três formatos que aparecem na fila:

- nacional:  padrão nacional (NFSe > infNFSe > DPS > infDPS), obrigatório desde 2026
- abrasf:    padrão ABRASF (CompNfse > Nfse > InfNfse), usado por muitas prefeituras até a migração
- sao_paulo: NFS-e da Prefeitura de São Paulo (NFe > ChaveNFe ...)

Todos viram o mesmo objeto NotaServico, então as regras fiscais não precisam saber de onde veio a nota.
Um arquivo pode ter mais de uma nota (retorno de consulta em lote); por isso a leitura devolve uma lista.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

from .nota import NotaServico
from .utils import ZERO, achar, data, item_lc116, numero, so_digitos, texto, xml_sem_ns


class XmlInvalido(Exception):
    """O arquivo não é uma NFS-e que dê para ler. A mensagem explica o motivo."""


# ---------------------------------------------------------------- diagnóstico
def diagnosticar(conteudo: bytes) -> str | None:
    """Explica por que o arquivo não serve, em vez de só dizer 'inválido'. None = parece NFS-e."""
    t = conteudo.decode("utf-8", "replace").lower()
    inicio = t.lstrip("﻿ \r\n\t")[:500]
    if not inicio:
        return "o arquivo está vazio"
    if inicio.startswith("<!doctype html") or "<html" in inicio:
        return "o arquivo é uma página da internet salva como .xml, não o XML da nota (baixe de novo)"
    if "<infnfe" in t and "<infnfse" not in t:
        return "é uma NF-e de produtos (DANFE), não uma nota de serviço"
    if "<evento" in t and "<infnfse" not in t and "<infdps" not in t:
        return "é um XML de evento (ex.: cancelamento), não a nota em si"
    if not any(m in t for m in ("<infnfse", "<infdps", "<compnfse", "<infnfse", "<nfse", "<chavenfe")):
        return "não foi encontrada nenhuma estrutura de NFS-e conhecida no arquivo"
    return None


def detectar_layout(raiz: ET.Element) -> str | None:
    if achar(raiz, "infNFSe", "infDPS") is not None:
        return "nacional"
    if achar(raiz, "InfNfse") is not None:
        return "abrasf"
    if raiz.tag == "NFe" or achar(raiz, "ChaveNFe") is not None:
        return "sao_paulo"
    return None


# ---------------------------------------------------------------- utilidades
def _percentual(valor: Decimal) -> Decimal:
    """Alíquota pode vir como fração (0.05) ou percentual (5.00). Sempre devolve percentual."""
    return valor * 100 if ZERO < valor < 1 else valor


def _liquido_calculado(n: NotaServico) -> Decimal:
    iss = n.valor_iss if n.iss_retido else ZERO
    return n.valor_servicos - iss - n.irrf_retido - n.pcc_retido - n.inss_retido


# ---------------------------------------------------------------- padrão nacional
def _ler_nacional(raiz: ET.Element, arquivo: str) -> list[NotaServico]:
    notas = []
    blocos = raiz.findall(".//infNFSe") or [raiz]
    for inf in blocos:
        dps = achar(inf, "infDPS")
        if dps is None:
            dps = achar(raiz, "infDPS")
        n = NotaServico(arquivo=arquivo, layout="nacional")

        n.numero = texto(inf, "./nNFSe")
        id_nota = inf.get("Id") or ""
        n.chave = so_digitos(id_nota) or None
        n.data_emissao = data(texto(dps, "dhEmi") or texto(inf, "./dhProc"))
        n.competencia = data(texto(dps, "dCompet"))

        emit = achar(inf, "./emit")
        n.cnpj_prestador = texto(emit, "CNPJ") or texto(dps, "prest/CNPJ")
        n.nome_prestador = texto(emit, "xNome") or texto(dps, "prest/xNome")
        toma = achar(dps, "toma")
        n.cnpj_tomador = texto(toma, "CNPJ")
        n.nome_tomador = texto(toma, "xNome")

        c_serv = achar(dps, "serv/cServ", "cServ")
        n.codigo_tributacao_nacional = texto(c_serv, "./cTribNac")
        n.codigo_municipal = texto(c_serv, "./cTribMun")
        n.descricao_servico = texto(c_serv, "./xDescServ") or texto(dps, "xDescServ")
        n.item_lc116 = item_lc116(n.codigo_tributacao_nacional)

        val_dps = dps.find("./valores") if dps is not None else None
        val_nfse = inf.find("./valores")
        n.valor_servicos = numero(val_dps, "vServPrest/vServ", "vServ")

        trib_mun = achar(val_dps, "trib/tribMun", "tribMun")
        # tpRetISSQN: 1 = não retido; 2 = retido pelo tomador; 3 = retido pelo intermediário
        n.iss_retido = texto(trib_mun, "./tpRetISSQN") in ("2", "3")
        n.base_calculo = numero(val_nfse, "./vBC") or n.valor_servicos
        n.aliquota_iss = _percentual(numero(val_nfse, "./pAliqAplic") or numero(trib_mun, "./pAliq"))
        n.valor_iss = numero(val_nfse, "./vISSQN")

        trib_fed = achar(val_dps, "trib/tribFed", "tribFed")
        n.irrf_retido = numero(trib_fed, "./vRetIRRF")
        n.inss_retido = numero(trib_fed, "./vRetCP")
        # No leiaute vigente, vRetCSLL traz a SOMA das retenções de PIS, COFINS e CSLL.
        n.pcc_retido = numero(trib_fed, "./vRetCSLL")

        n.valor_liquido = numero(val_nfse, "./vLiq") or _liquido_calculado(n)
        notas.append(n)
    return notas


# ---------------------------------------------------------------- ABRASF
def _ler_abrasf(raiz: ET.Element, arquivo: str) -> list[NotaServico]:
    notas = []
    # Cada CompNfse é uma nota; um cancelamento fica dentro do mesmo CompNfse
    compostos = raiz.findall(".//CompNfse") or [raiz]
    for comp in compostos:
        inf = achar(comp, "InfNfse")
        if inf is None:
            continue
        n = NotaServico(arquivo=arquivo, layout="abrasf")
        n.numero = texto(inf, "./Numero")
        n.chave = texto(inf, "./CodigoVerificacao")
        n.data_emissao = data(texto(inf, "./DataEmissao"))
        n.competencia = data(texto(inf, "Competencia"))
        n.cancelada = achar(comp, "NfseCancelamento") is not None

        prest = achar(inf, "PrestadorServico", "Prestador")
        n.cnpj_prestador = texto(prest, "Cnpj")
        n.nome_prestador = texto(prest, "RazaoSocial") or texto(inf, "RazaoSocial")
        toma = achar(inf, "TomadorServico", "Tomador")
        n.cnpj_tomador = texto(toma, "Cnpj")
        n.nome_tomador = texto(toma, "RazaoSocial")

        serv = achar(inf, "Servico")
        val = achar(serv, "./Valores")
        val_nfse = achar(inf, "./ValoresNfse")   # versão 2.x repete alguns totais aqui

        n.item_lc116 = item_lc116(texto(serv, "./ItemListaServico"))
        n.codigo_municipal = texto(serv, "./CodigoTributacaoMunicipio")
        n.descricao_servico = texto(serv, "./Discriminacao")

        n.valor_servicos = numero(val, "./ValorServicos")
        n.base_calculo = numero(val, "./BaseCalculo") or numero(val_nfse, "./BaseCalculo") or n.valor_servicos
        n.aliquota_iss = _percentual(numero(val, "./Aliquota") or numero(val_nfse, "./Aliquota"))
        n.valor_iss = numero(val, "./ValorIss") or numero(val_nfse, "./ValorIss")
        # IssRetido: 1 = sim, 2 = não (fica em Valores na 1.0 e em Servico na 2.x)
        n.iss_retido = (texto(serv, "./IssRetido") or texto(val, "./IssRetido")) == "1"

        n.irrf_retido = numero(val, "./ValorIr")
        n.inss_retido = numero(val, "./ValorInss")
        n.pcc_retido = numero(val, "./ValorPis") + numero(val, "./ValorCofins") + numero(val, "./ValorCsll")
        n.valor_liquido = (numero(val, "./ValorLiquidoNfse") or numero(val_nfse, "./ValorLiquidoNfse")
                           or _liquido_calculado(n))
        notas.append(n)
    return notas


# ---------------------------------------------------------------- Prefeitura de São Paulo
def _ler_sao_paulo(raiz: ET.Element, arquivo: str) -> list[NotaServico]:
    notas = []
    for nfe in ([raiz] if raiz.tag == "NFe" else raiz.findall(".//NFe")):
        n = NotaServico(arquivo=arquivo, layout="sao_paulo")
        n.numero = texto(nfe, "ChaveNFe/NumeroNFe")
        n.chave = texto(nfe, "ChaveNFe/CodigoVerificacao")
        n.data_emissao = data(texto(nfe, "./DataEmissaoNFe"))
        n.competencia = data(texto(nfe, "./DataFatoGeradorNFe"))
        n.cancelada = (texto(nfe, "./StatusNFe") or "").upper() == "C"

        n.cnpj_prestador = texto(nfe, "CPFCNPJPrestador/CNPJ")
        n.nome_prestador = texto(nfe, "./RazaoSocialPrestador")
        n.cnpj_tomador = texto(nfe, "CPFCNPJTomador/CNPJ")
        n.nome_tomador = texto(nfe, "./RazaoSocialTomador")

        # São Paulo usa código municipal de 5 dígitos (ex.: 07498), não o item da LC 116
        n.codigo_municipal = texto(nfe, "./CodigoServico")
        n.descricao_servico = texto(nfe, "./Discriminacao")

        n.valor_servicos = numero(nfe, "./ValorServicos")
        n.base_calculo = n.valor_servicos - numero(nfe, "./ValorDeducoes")
        n.aliquota_iss = _percentual(numero(nfe, "./AliquotaServicos"))
        n.valor_iss = numero(nfe, "./ValorISS")
        n.iss_retido = (texto(nfe, "./ISSRetido") or "").lower() in ("true", "s", "1")

        n.irrf_retido = numero(nfe, "./ValorIR")
        n.inss_retido = numero(nfe, "./ValorINSS")
        if texto(nfe, "./RetencaoPisCofins") is not None:
            # leiaute novo: ValorCSLL já é a soma de PIS + COFINS + CSLL retidos
            n.pcc_retido = numero(nfe, "./ValorCSLL")
        else:
            n.pcc_retido = numero(nfe, "./ValorPIS") + numero(nfe, "./ValorCOFINS") + numero(nfe, "./ValorCSLL")
        n.valor_liquido = _liquido_calculado(n)
        notas.append(n)
    return notas


LEITORES = {"nacional": _ler_nacional, "abrasf": _ler_abrasf, "sao_paulo": _ler_sao_paulo}


def ler_xml(conteudo: bytes, arquivo: str = "xml") -> list[NotaServico]:
    motivo = diagnosticar(conteudo)
    if motivo:
        raise XmlInvalido(motivo)
    try:
        raiz = xml_sem_ns(conteudo)
    except ET.ParseError as erro:
        raise XmlInvalido(f"o XML está com a estrutura quebrada ({erro}); o arquivo pode ter sido cortado") from erro

    layout = detectar_layout(raiz)
    if layout is None:
        raise XmlInvalido("layout de NFS-e não reconhecido (nem nacional, nem ABRASF, nem São Paulo)")
    notas = LEITORES[layout](raiz, arquivo)
    if not notas:
        raise XmlInvalido(f"layout {layout} reconhecido, mas nenhuma nota foi encontrada no arquivo")
    return notas


def ler_arquivo(caminho: str | Path) -> list[NotaServico]:
    caminho = Path(caminho)
    return ler_xml(caminho.read_bytes(), caminho.name)
