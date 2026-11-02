"""API HTTP do extrator. É o que o fluxo do n8n chama.

Rodar:  uvicorn api:app --reload
Docs:   http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel

load_dotenv()

from extrator import ResultadoExtracao, criar_provedor, extrair_nota  # noqa: E402
from extrator.leitor import EXTENSOES_SUPORTADAS, ler_texto  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(
    title="Extrator de Notas com IA",
    description="Extrai fornecedor, CNPJ, valores e datas de notas fiscais e sinaliza o que precisa de revisão humana.",
    version="1.0.0",
)
provedor = criar_provedor()


class EntradaTexto(BaseModel):
    texto: str
    arquivo: str = "texto"


@app.get("/saude")
def saude() -> dict:
    return {"status": "ok", "provedor": provedor.nome}


@app.post("/extrair", response_model=ResultadoExtracao)
def extrair_texto(entrada: EntradaTexto) -> ResultadoExtracao:
    if not entrada.texto.strip():
        raise HTTPException(status_code=422, detail="Texto da nota vazio")
    return extrair_nota(entrada.texto, provedor, arquivo=entrada.arquivo)


@app.post("/extrair/arquivo", response_model=ResultadoExtracao)
async def extrair_arquivo(arquivo: UploadFile) -> ResultadoExtracao:
    extensao = Path(arquivo.filename or "").suffix.lower()
    if extensao not in EXTENSOES_SUPORTADAS:
        raise HTTPException(status_code=415, detail=f"Envie um arquivo {', '.join(sorted(EXTENSOES_SUPORTADAS))}")

    with tempfile.TemporaryDirectory() as pasta:
        caminho = Path(pasta) / f"nota{extensao}"
        caminho.write_bytes(await arquivo.read())
        try:
            texto = ler_texto(caminho)
        except ValueError as erro:
            raise HTTPException(status_code=422, detail=str(erro)) from erro

    return extrair_nota(texto, provedor, arquivo=arquivo.filename or "arquivo")
