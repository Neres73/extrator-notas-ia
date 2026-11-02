"""Regras que decidem o destino de cada nota.

OK        nota confere com a base de parâmetros; nada a fazer
CORRIGIR  divergência objetiva (imposto retido diferente do esperado, PLU errado) -> gera pedido de correção
REVISAR   a regra não consegue decidir sozinha (código fora da base, nota cancelada, XML ausente...)

Só CORRIGIR vira lançamento no SAP. REVISAR é a lista de exceções, com o motivo de cada uma.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from .config import Config
from .nota import NotaServico
from .planilhas import LinhaFila, ParametroFiscal
from .utils import ZERO, cnpj_valido, so_digitos

CENTAVO = Decimal("0.01")


@dataclass
class Divergencia:
    campo: str
    esperado: str
    na_nota: str
    origem: str = "na nota"     # onde está o valor divergente


@dataclass
class Resultado:
    status: str                                   # OK / CORRIGIR / REVISAR
    nota: NotaServico | None
    fila: LinhaFila | None = None
    parametro: ParametroFiscal | None = None
    motivos: list[str] = field(default_factory=list)
    divergencias: list[Divergencia] = field(default_factory=list)
    esperado: dict[str, Decimal] = field(default_factory=dict)

    @property
    def plu_correto(self) -> str | None:
        return self.parametro.plu if self.parametro else None


def retencao_esperada(base: Decimal, percentual: Decimal, config: Config) -> Decimal:
    valor = (base * percentual / 100).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    return ZERO if valor < config.valor_minimo_retencao else valor


def _rs(v: Decimal) -> str:
    return f"{v:.2f}".replace(".", ",")


def conferir(nota: NotaServico, candidatos: list[ParametroFiscal], config: Config,
             fila: LinhaFila | None = None) -> Resultado:
    r = Resultado(status="OK", nota=nota, fila=fila)

    # ---- condições que impedem decidir automaticamente
    if nota.cancelada:
        r.motivos.append("Nota cancelada na prefeitura")
    if not cnpj_valido(nota.cnpj_prestador):
        r.motivos.append(f"CNPJ do prestador ausente ou inválido: {nota.cnpj_prestador or '-'}")
    if config.cnpj_raiz_tomador and not so_digitos(nota.cnpj_tomador).startswith(so_digitos(config.cnpj_raiz_tomador)):
        r.motivos.append(f"Tomador não é a empresa: {nota.cnpj_tomador or '-'} {nota.nome_tomador or ''}".strip())
    if nota.valor_servicos <= 0:
        r.motivos.append("Valor dos serviços zerado ou ausente no XML")

    codigo = nota.item_lc116 or nota.codigo_municipal
    if not candidatos:
        r.motivos.append(f"Código de serviço {codigo or '(não informado)'} não está na base de parâmetros")
    elif len({p.plu for p in candidatos}) > 1:
        plus = ", ".join(sorted({p.plu for p in candidatos}))
        r.motivos.append(f"Código {codigo} tem mais de um PLU na base ({plus}); falta critério para escolher")
    else:
        r.parametro = candidatos[0]

    if r.motivos:
        r.status = "REVISAR"
        return r

    # ---- comparação com o parâmetro fiscal
    p = r.parametro
    base = nota.valor_servicos
    for campo, percentual, na_nota in (("IRRF", p.irrf, nota.irrf_retido),
                                       ("PIS/COFINS/CSLL", p.pcc, nota.pcc_retido),
                                       ("INSS", p.inss, nota.inss_retido)):
        esperado = retencao_esperada(base, percentual, config)
        r.esperado[campo] = esperado
        if abs(esperado - na_nota) > config.tolerancia:
            r.divergencias.append(Divergencia(
                campo, f"R$ {_rs(esperado)} ({percentual:g}%)", f"R$ {_rs(na_nota)}"))

    if p.retem_iss is not None and p.retem_iss != nota.iss_retido:
        r.divergencias.append(Divergencia(
            "ISS retido", "sim" if p.retem_iss else "não", "sim" if nota.iss_retido else "não"))

    if fila and fila.plu_atual and fila.plu_atual.strip() != p.plu:
        r.divergencias.append(Divergencia("PLU do pedido", p.plu, fila.plu_atual, origem="no pedido"))

    # conferência interna do XML: ISS informado x base x alíquota (só alerta, quem calcula é a prefeitura)
    if nota.aliquota_iss and nota.valor_iss:
        iss_calc = (nota.base_calculo * nota.aliquota_iss / 100).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        if abs(iss_calc - nota.valor_iss) > config.tolerancia:
            nota.avisos.append(f"ISS do XML (R$ {_rs(nota.valor_iss)}) difere de base x alíquota (R$ {_rs(iss_calc)})")

    if r.divergencias:
        r.status = "CORRIGIR"
        r.motivos = [f"{d.campo}: esperado {d.esperado}, {d.origem} {d.na_nota}" for d in r.divergencias]
    return r


def sem_xml(fila: LinhaFila, motivo: str) -> Resultado:
    return Resultado(status="REVISAR", nota=None, fila=fila, motivos=[motivo])
