"""Leitura do texto bruto de uma nota (PDF com texto ou arquivo .txt)."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

EXTENSOES_SUPORTADAS = {".pdf", ".txt"}


def ler_texto(caminho: str | Path) -> str:
    caminho = Path(caminho)
    extensao = caminho.suffix.lower()

    if extensao == ".txt":
        return caminho.read_text(encoding="utf-8")

    if extensao == ".pdf":
        leitor = PdfReader(str(caminho))
        paginas = [pagina.extract_text() or "" for pagina in leitor.pages]
        texto = "\n".join(paginas).strip()
        if not texto:
            raise ValueError(
                f"{caminho.name}: o PDF não tem texto selecionável (provavelmente é imagem escaneada)."
            )
        return texto

    raise ValueError(f"Formato não suportado: {extensao}. Use {', '.join(sorted(EXTENSOES_SUPORTADAS))}.")


def listar_arquivos(pasta_ou_arquivo: str | Path) -> list[Path]:
    caminho = Path(pasta_ou_arquivo)
    if caminho.is_file():
        return [caminho]
    return sorted(p for p in caminho.iterdir() if p.suffix.lower() in EXTENSOES_SUPORTADAS)
