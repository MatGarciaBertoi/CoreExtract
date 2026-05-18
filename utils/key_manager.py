"""
Gerencia a chave Gemini embutida no executável distribuído.

Funciona em dois modos:
  1. MANAGED (distribuição): chave codificada via XOR+base64 em managed_key.py
     → gerado pelo prepare_build.py antes do PyInstaller
     → NÃO commitado no git (está no .gitignore)
  2. USER (dev / configuração manual): chave digitada pelo usuário nas Settings

Segurança:
  A obfuscação XOR impede leitura trivial do binário (strings, hex dump),
  mas não é criptografia forte. Para um produto B2B vendido a empresas de RH
  confiáveis, é suficiente. Se a chave vazar, basta gerar uma nova em
  aistudio.google.com e rodar prepare_build.py novamente.
"""
from __future__ import annotations

import base64

_SALT = b"BTExtract-BertoiInformatica-2025-RH"


def encode_key(plain_key: str) -> str:
    """Codifica a chave para armazenar em managed_key.py."""
    data = plain_key.encode("utf-8")
    salt = (_SALT * (len(data) // len(_SALT) + 1))[: len(data)]
    xored = bytes(a ^ b for a, b in zip(data, salt))
    return base64.b64encode(xored).decode("ascii")


def decode_key(encoded: str) -> str:
    """Decodifica a chave embutida em managed_key.py."""
    data = base64.b64decode(encoded.encode("ascii"))
    salt = (_SALT * (len(data) // len(_SALT) + 1))[: len(data)]
    return bytes(a ^ b for a, b in zip(data, salt)).decode("utf-8")


def get_managed_key() -> str | None:
    """
    Retorna a chave gerenciada se managed_key.py existir,
    ou None se o usuário deve configurar a própria chave.
    """
    try:
        from utils import managed_key  # noqa: PLC0415
        raw = getattr(managed_key, "ENCODED_KEY", None)
        if raw:
            return decode_key(raw)
    except ImportError:
        pass
    return None


def is_managed() -> bool:
    """True quando a chave Gemini está gerenciada pelo distribuidor."""
    return get_managed_key() is not None
