from typing import Any


def build_extraction_result(
    filename: str,
    file_type: str,
    extraction_method: str,
    text: str = "",
    records: list[dict[str, Any]] | None = None,
    tables: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "filename": filename,
        "file_type": file_type,
        "extraction_method": extraction_method,
        "text": text,
        "records": records or [],
        "tables": tables or [],
        "metadata": metadata or {},
        "warnings": warnings or [],
    }
