"""Extração de texto de arquivos PDF usando pdfplumber."""
import io
import pdfplumber


def extract_pdf(file_bytes: bytes) -> str:
    """
    Extrai texto de um PDF, página por página.
    pdfplumber preserva melhor o layout e tabelas do que PyPDF2.
    """
    text_parts: list[str] = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if page_text:
                text_parts.append(f"[Página {i}]\n{page_text.strip()}")

            # Extrai tabelas como texto estruturado (útil para experiências tabulares)
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    row_text = " | ".join(cell or "" for cell in row if cell)
                    if row_text.strip():
                        text_parts.append(row_text)

    return "\n\n".join(text_parts)
