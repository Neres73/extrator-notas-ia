"""Lançamento dos pedidos de correção no SAP (SAP GUI Scripting).

ESTADO: a conexão com o SAP e o laço de lançamento estão prontos. Falta só o passo a passo da
transação de correção (`_preencher_transacao`), que precisa vir das macros que a equipe já usa
ou de uma gravação do SAP GUI (Layout local > Gravação e reprodução de script) de UM pedido de correção.
Não invente os IDs dos campos: eles mudam de transação para transação e de ambiente para ambiente.

Por padrão roda em SIMULAÇÃO: mostra o que seria lançado e não toca no SAP.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .regras import Resultado
from .utils import moeda


@dataclass
class RetornoLancamento:
    nota: str
    sucesso: bool
    mensagem: str
    documento: str | None = None


def conectar_sap():
    """Usa a sessão do SAP GUI que já está aberta e logada (não guarda senha)."""
    import win32com.client  # pywin32, só existe no Windows

    try:
        engine = win32com.client.GetObject("SAPGUI").GetScriptingEngine
    except Exception as erro:  # noqa: BLE001
        raise RuntimeError("SAP GUI não encontrado. Abra o SAP e faça login antes de rodar.") from erro
    if engine.Children.Count == 0:
        raise RuntimeError("Nenhuma conexão aberta no SAP GUI.")
    conexao = engine.Children(0)
    if conexao.Children.Count == 0:
        raise RuntimeError("Nenhuma sessão aberta na conexão do SAP.")
    return conexao.Children(0)


def _preencher_transacao(sessao, r: Resultado) -> str:
    """Lança UM pedido de correção e devolve o número do documento criado.

    Substituir pelo roteiro gravado da transação. Estrutura esperada:
        sessao.findById("wnd[0]/tbar[0]/okcd").text = "/n<TRANSAÇÃO>"
        sessao.findById("wnd[0]").sendVKey(0)
        ... preencher campos com r.nota, r.plu_correto, r.esperado ...
        sessao.findById("wnd[0]/tbar[0]/btn[11]").press()     # salvar
        return sessao.findById("wnd[0]/sbar").text             # mensagem com o nº do documento
    """
    raise NotImplementedError(
        "Roteiro da transação de correção ainda não configurado: envie as macros atuais ou "
        "uma gravação do SAP GUI de um pedido de correção."
    )


def _mensagem_barra(sessao) -> tuple[str, str]:
    barra = sessao.findById("wnd[0]/sbar")
    return barra.messageType, barra.text      # tipo: S = sucesso, E = erro, W = aviso


def lancar(resultados: list[Resultado], simulacao: bool = True, pausa: float = 0.5) -> list[RetornoLancamento]:
    pedidos = [r for r in resultados if r.status == "CORRIGIR"]
    retornos: list[RetornoLancamento] = []

    if simulacao:
        print(f"\nSIMULAÇÃO: {len(pedidos)} pedido(s) de correção seriam lançados (nada foi enviado ao SAP)\n")
        for r in pedidos:
            n = r.nota
            print(f"  NFS-e {n.numero:<8} {(n.nome_prestador or '')[:35]:<35} PLU {r.plu_correto:<10} "
                  f"{moeda(n.valor_servicos):>14}")
            for m in r.motivos:
                print(f"      - {m}")
            retornos.append(RetornoLancamento(n.numero or "", True, "simulação"))
        return retornos

    sessao = conectar_sap()
    for r in pedidos:
        n = r.nota
        try:
            documento = _preencher_transacao(sessao, r)
            tipo, texto = _mensagem_barra(sessao)
            ok = tipo in ("S", "")
            retornos.append(RetornoLancamento(n.numero or "", ok, texto, documento if ok else None))
            print(f"  {'✔' if ok else '✖'} NFS-e {n.numero}: {texto}")
        except NotImplementedError:
            raise
        except Exception as erro:  # noqa: BLE001 - registra e segue para a próxima nota
            retornos.append(RetornoLancamento(n.numero or "", False, f"erro: {erro}"))
            print(f"  ✖ NFS-e {n.numero}: {erro}")
            try:
                sessao.findById("wnd[0]/tbar[0]/okcd").text = "/n"
                sessao.findById("wnd[0]").sendVKey(0)
            except Exception:  # noqa: BLE001
                pass
        time.sleep(pausa)
    return retornos
