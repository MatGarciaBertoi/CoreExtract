"""Extração de texto de planilhas XLSX/XLS usando pandas + openpyxl."""
import io
import pandas as pd


def extract_xlsx(file_bytes: bytes) -> str:
    """
    Lê todas as abas da planilha e serializa como texto tabular.
    Útil para currículos em formato de planilha (menos comum, mas existe).
    """
    text_parts: list[str] = []

    excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")

    for sheet_name in excel_file.sheet_names:
        df = excel_file.parse(sheet_name, header=None, dtype=str)
        df.fillna("", inplace=True)

        # Remove linhas completamente vazias
        df = df[df.apply(lambda row: row.str.strip().any(), axis=1)]

        if df.empty:
            continue

        text_parts.append(f"[Aba: {sheet_name}]")
        for _, row in df.iterrows():
            row_text = " | ".join(str(v).strip() for v in row if str(v).strip())
            if row_text:
                text_parts.append(row_text)

    return "\n".join(text_parts)
