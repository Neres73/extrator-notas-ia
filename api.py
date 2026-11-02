"""API: manda o PDF da nota e o código SAP do fornecedor, recebe o PLU sugerido e o motivo.

É o que o formulário do n8n chama. Usa o mesmo config.json (ou config.exemplo.json) da planilha.

Rodar:  uvicorn api:app --reload
Docs:   http://localhost:8000/docs
"""

from __future__ import annotations

import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile

from plu.servico import analisar, carregar_json, montar

PASTA = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(PASTA / ".env")
except ImportError:
    pass

_cfg_arquivo = PASTA / "config.json" if (PASTA / "config.json").exists() else PASTA / "config.exemplo.json"
CONF = montar(carregar_json(_cfg_arquivo), PASTA)

app = FastAPI(
    title="Assistente de PLU para NFS-e",
    description="Lê a NFS-e (PDF), aplica a base de parâmetros fiscais e sugere o PLU da ordem de manutenção.",
    version="2.0.0",
)


@app.get("/saude")
def saude() -> dict:
    return {"status": "ok", "fornecedores": len(CONF.base.prestadores), "plus": len(CONF.base.plus),
            "ia": CONF.provedor_ia.nome if CONF.provedor_ia else "desligada"}


@app.post("/sugerir-plu")
async def sugerir_plu(nota: UploadFile, fornecedor: str = Form(...), preco: str | None = Form(None)) -> dict:
    if not (nota.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Envie o PDF da NFS-e")
    valor = None
    if preco and preco.strip():
        texto = preco.strip().replace("R$", "").strip()
        if "," in texto:                     # formato brasileiro: 1.234,56
            texto = texto.replace(".", "").replace(",", ".")
        try:
            valor = Decimal(texto)
        except InvalidOperation as erro:
            raise HTTPException(status_code=422, detail=f"Preço inválido: {preco}") from erro

    with tempfile.TemporaryDirectory() as pasta:
        caminho = Path(pasta) / "nota.pdf"
        caminho.write_bytes(await nota.read())
        escolha, lida = analisar(caminho, fornecedor.strip(), valor, CONF)

    return {
        "status": escolha.status,
        "plu": escolha.plu,
        "motivo": escolha.motivo,
        "opcoes": escolha.opcoes,
        "fornecedor": CONF.base.nomes.get(fornecedor.strip().lstrip("0")),
        "nota": None if lida is None else {
            "codigo_servico": lida.item_lc116,
            "codigo_municipal": lida.codigo_municipal,
            "valor_servicos": float(lida.valor_servicos) if lida.valor_servicos is not None else None,
            "tributacao": str(lida.tributacao(valor)) if lida.leu_retencoes else None,
            "lido_pela_ia": lida.lido_pela_ia,
            "avisos": lida.avisos,
        },
    }
