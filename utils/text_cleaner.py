"""
Normalização e limpeza do texto bruto extraído dos arquivos.
Texto sujo (quebras aleatórias, espaços duplos, caracteres de controle)
degrada significativamente a qualidade da resposta do Gemini.
"""
import re
import unicodedata


def clean_extracted_text(text: str) -> str:
    """
    Pipeline de limpeza aplicado antes de enviar ao modelo de IA.

    Etapas:
    1. Normaliza encoding Unicode (NFC)
    2. Remove caracteres de controle e não-imprimíveis
    3. Colapsa múltiplos espaços/tabs em um único espaço
    4. Normaliza quebras de linha (máx. 2 consecutivas)
    5. Remove linhas compostas apenas por símbolos repetidos (----, ====, ...)
    6. Remove cabeçalhos de paginação típicos de PDF (ex: "Página 1 de 10")
    7. Strip geral
    """
    if not text:
        return ""

    # 1. Normalização Unicode
    text = unicodedata.normalize("NFC", text)

    # 2. Remove caracteres de controle (mantém \n e \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    # 3. Substitui tabs por espaço
    text = text.replace("\t", " ")

    # 4. Colapsa múltiplos espaços
    text = re.sub(r" {2,}", " ", text)

    # 5. Normaliza quebras de linha
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 6. Remove linhas de separação decorativas (---- ==== .... ####)
    text = re.sub(r"^[\-=_#*~.]{3,}\s*$", "", text, flags=re.MULTILINE)

    # 7. Remove marcadores de página de PDF
    text = re.sub(
        r"(?i)\b(página|page|pág\.?)\s*\d+\s*(de|of|/)\s*\d+\b",
        "", text
    )

    # 8. Remove linhas em branco no início/fim de seções
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def truncate_for_model(text: str, max_chars: int = 25_000) -> tuple[str, bool]:
    """
    Trunca o texto para o limite de contexto e informa se houve truncamento.
    Tenta cortar em um parágrafo para não quebrar no meio de uma frase.

    Returns:
        (texto_truncado, foi_truncado)
    """
    if len(text) <= max_chars:
        return text, False

    # Tenta encontrar o último parágrafo antes do limite
    cutoff = text.rfind("\n\n", 0, max_chars)
    if cutoff == -1:
        cutoff = text.rfind("\n", 0, max_chars)
    if cutoff == -1:
        cutoff = max_chars

    return text[:cutoff].strip(), True
