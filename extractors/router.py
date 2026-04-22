"""
Roteador de extração: detecta o formato pelo nome do arquivo e
delega para o extrator correto.
"""
from pathlib import Path

from .pdf_extractor import extract_pdf
from .docx_extractor import extract_docx
from .xlsx_extractor import extract_xlsx
from .txt_extractor import extract_txt


def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    Recebe os bytes do arquivo e seu nome, retorna o texto bruto extraído.

    Raises:
        ValueError: formato não suportado.
    """
    ext = Path(filename).suffix.lower()

    extractors = {
        ".pdf": extract_pdf,
        ".docx": extract_docx,
        ".xlsx": extract_xlsx,
        ".xls": extract_xlsx,
        ".txt": extract_txt,
    }

    handler = extractors.get(ext)
    if not handler:
        raise ValueError(f"Formato '{ext}' não suportado. Use: {list(extractors)}")

    return handler(file_bytes)
