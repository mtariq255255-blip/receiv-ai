from io import BytesIO
from pathlib import Path

from docx import Document

from app.services.extraction_result import build_extraction_result


def extract_word(
    file_bytes: bytes,
    filename: str = "invoice.docx",
) -> dict:
    if not file_bytes:
        raise ValueError("The Word document is empty.")
    if Path(filename).suffix.lower() != ".docx":
        raise ValueError("Only DOCX Word documents are supported.")

    try:
        document = Document(BytesIO(file_bytes))
    except Exception as exc:
        raise ValueError(
            "Unable to read the Word document. "
            "Make sure it is a valid DOCX file."
        ) from exc

    text_parts = []
    for paragraph in document.paragraphs:
        value = paragraph.text.strip()
        if value:
            text_parts.append(value)

    tables = []
    for table_index, table in enumerate(document.tables, start=1):
        table_rows = [
            [cell.text.strip() for cell in row.cells]
            for row in table.rows
        ]
        tables.append({
            "table_number": table_index,
            "rows": table_rows,
        })
        text_parts.extend(" | ".join(row) for row in table_rows)

    full_text = "\n".join(text_parts)
    warnings = []
    if not full_text.strip():
        warnings.append("No readable text or tables were found.")

    return build_extraction_result(
        filename=filename,
        file_type="docx",
        extraction_method="python_docx",
        text=full_text,
        tables=tables,
        metadata={
            "paragraph_count": len(document.paragraphs),
            "table_count": len(document.tables),
        },
        warnings=warnings,
    )
