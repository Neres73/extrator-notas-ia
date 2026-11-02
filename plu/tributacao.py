"""Tributação federal: a da base fiscal (texto como 'IR 1,5% e PCC') e a destacada na nota (valores em R$).

As duas viram o mesmo objeto, então dá para comparar direto.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

ALIQUOTAS_IR = (Decimal("1"), Decimal("1.5"))
ALIQUOTAS_INSS = (Decimal("11"), Decimal("3.5"))


def normalizar(texto: str | None) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t.lower()).strip()


@dataclass(frozen=True)
class Tributacao:
    ir: Decimal | None = None        # alíquota de IR retido (1 ou 1,5) ou None
    pcc: bool = False                # PIS/COFINS/CSLL retidos
    inss: Decimal | None = None      # alíquota de INSS retido (11 ou 3,5) ou None
    pessoa_fisica: bool = False

    def __str__(self) -> str:
        if self.pessoa_fisica:
            return "Pessoa Física"
        partes = []
        if self.ir is not None:
            partes.append(f"IR {self.ir.normalize():f}%".replace(".", ","))
        if self.pcc:
            partes.append("PCC")
        if self.inss is not None:
            partes.append(f"INSS {self.inss.normalize():f}%".replace(".", ","))
        return " e ".join(partes) if partes else "Sem Imp. Fed."

    @classmethod
    def do_texto(cls, texto: str | None) -> "Tributacao":
        """'IR 1,5% e PCC' / 'PCC e INSS 11%' / 'Sem Imp. Fed.' / 'IR 1,5%, PIS, COFINS e INSS 3,5%'."""
        t = normalizar(texto)
        if "pessoa fisica" in t:
            return cls(pessoa_fisica=True)
        if not t or "sem imp" in t:
            return cls()
        ir = re.search(r"\bir\s*(\d+(?:[.,]\d+)?)\s*%", t)
        inss = re.search(r"inss\s*(\d+(?:[.,]\d+)?)\s*%", t)
        pcc = "pcc" in t or ("pis" in t or "cofins" in t or re.search(r"\bcs\b|csll", t) is not None)
        return cls(
            ir=Decimal(ir.group(1).replace(",", ".")) if ir else None,
            pcc=bool(pcc),
            inss=Decimal(inss.group(1).replace(",", ".")) if inss else None,
        )

    @classmethod
    def dos_valores(cls, base: Decimal, ir: Decimal, pcc: Decimal, inss: Decimal) -> "Tributacao":
        """Valores retidos na nota -> alíquotas. Aproxima para a alíquota legal mais próxima."""
        def aliquota(valor: Decimal, opcoes: tuple[Decimal, ...]) -> Decimal | None:
            if valor <= 0 or base <= 0:
                return None
            percentual = valor / base * 100
            return min(opcoes, key=lambda a: abs(a - percentual))

        return cls(ir=aliquota(ir, ALIQUOTAS_IR), pcc=pcc > 0, inss=aliquota(inss, ALIQUOTAS_INSS))
