"""Extração de texto puro de arquivos TXT."""


def extract_txt(file_bytes: bytes) -> str:
    """
    Decodifica o arquivo tentando UTF-8 primeiro, com fallback para latin-1.
    """
    try:
        return file_bytes.decode("utf-8").strip()
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1").strip()
