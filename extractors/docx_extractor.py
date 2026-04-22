"""Extração de texto de arquivos DOCX usando python-docx."""
import io
from docx import Document
from docx.oxml.ns import qn


def extract_docx(file_bytes: bytes) -> str:
    """
    Extrai parágrafos e tabelas de um documento Word.
    Preserva a ordem de leitura natural do documento.
    """
    doc = Document(io.BytesIO(file_bytes))
    text_parts: list[str] = []

    # Itera sobre o corpo do documento respeitando a ordem dos elementos
    for element in doc.element.body:
        tag = element.tag.split("}")[-1]  # remove namespace

        if tag == "p":
            # Parágrafo normal
            para_text = "".join(run.text for run in element.iterchildren(qn("w:r"))
                                if hasattr(run, "text") and run.text)
            # Fallback: leitura direta do XML
            if not para_text:
                para_text = element.text_content() if hasattr(element, "text_content") else ""
            if para_text.strip():
                text_parts.append(para_text.strip())

        elif tag == "tbl":
            # Tabela → serializa como linhas separadas por pipe
            for row in element.iterchildren(qn("w:tr")):
                cells = [
                    "".join(n.text or "" for n in cell.iter())
                    for cell in row.iterchildren(qn("w:tc"))
                ]
                row_text = " | ".join(c.strip() for c in cells if c.strip())
                if row_text:
                    text_parts.append(row_text)

    return "\n".join(text_parts)
