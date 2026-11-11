from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.extraction_result import build_extraction_result


def _cell_merge_info(cell: Any) -> dict[str, Any]:
    properties = cell._tc.tcPr
    grid_span = properties.gridSpan
    vertical_merge = properties.vMerge
    return {
        "grid_span": int(grid_span.val) if grid_span is not None else 1,
        "vertical_merge": (
            str(vertical_merge.val or "continue")
            if vertical_merge is not None
            else None
        ),
    }


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

    tables: list[dict[str, Any]] = []
    paragraphs: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    text_parts: list[str] = []
    block_number = 0

    def add_table(table: Table, parent: dict | None = None) -> str:
        nonlocal block_number
        block_number += 1
        table_number = len(tables) + 1
        record: dict[str, Any] = {
            "table_number": table_number,
            "rows": [],
            "cells": [],
            "column_count": len(table.columns),
            "parent_table": parent.get("table_number") if parent else None,
            "parent_row": parent.get("row_index") if parent else None,
            "parent_column": parent.get("column_index") if parent else None,
        }
        tables.append(record)
        blocks.append({"block_number": block_number, "type": "table", "table_number": table_number})

        for row_index, row in enumerate(table.rows, start=1):
            row_values: list[str] = []
            cell_records: list[dict[str, Any]] = []
            seen_cells: set[int] = set()
            logical_column = 1
            for cell in row.cells:
                cell_key = id(cell._tc)
                merge = _cell_merge_info(cell)
                if cell_key in seen_cells:
                    logical_column += merge["grid_span"]
                    continue
                seen_cells.add(cell_key)

                cell_paragraphs: list[str] = []
                nested_tables: list[int] = []
                for block in cell.iter_inner_content():
                    if isinstance(block, Paragraph):
                        value = block.text.strip()
                        if value:
                            cell_paragraphs.append(value)
                            block_number += 1
                            paragraphs.append({
                                "paragraph_number": len(paragraphs) + 1,
                                "text": value,
                                "block_number": block_number,
                                "table_number": table_number,
                                "row_index": row_index,
                                "column_index": logical_column,
                            })
                            blocks.append({
                                "block_number": block_number,
                                "type": "paragraph",
                                "paragraph_number": len(paragraphs),
                            })
                    elif isinstance(block, Table):
                        nested = add_table(block, {
                            "table_number": table_number,
                            "row_index": row_index,
                            "column_index": logical_column,
                        })
                        nested_tables.append(int(nested))

                cell_text = "\n".join(cell_paragraphs).strip()
                row_values.append(cell_text)
                cell_records.append({
                    "row_index": row_index,
                    "column_index": logical_column,
                    "text": cell_text,
                    "nested_tables": nested_tables,
                    **merge,
                })
                logical_column += merge["grid_span"]

            record["rows"].append(row_values)
            record["cells"].append(cell_records)

        text_parts.extend(
            " | ".join(value for value in row if value)
            for row in record["rows"]
            if any(row)
        )
        return str(table_number)

    try:
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                value = block.text.strip()
                if value:
                    block_number += 1
                    paragraphs.append({
                        "paragraph_number": len(paragraphs) + 1,
                        "text": value,
                        "block_number": block_number,
                        "table_number": None,
                        "row_index": None,
                        "column_index": None,
                    })
                    blocks.append({
                        "block_number": block_number,
                        "type": "paragraph",
                        "paragraph_number": len(paragraphs),
                    })
                    text_parts.append(value)
            elif isinstance(block, Table):
                add_table(block)
    except Exception as exc:
        raise ValueError(
            "Unable to extract paragraphs and tables from the Word document."
        ) from exc

    full_text = "\n".join(text_parts)
    warnings = []
    if not full_text.strip():
        warnings.append("No readable text or tables were found.")

    result = build_extraction_result(
        filename=filename,
        file_type="docx",
        extraction_method="python_docx",
        text=full_text,
        tables=tables,
        metadata={
            "paragraph_count": len(paragraphs),
            "table_count": len(tables),
            "top_level_table_count": len(document.tables),
            "block_count": block_number,
        },
        warnings=warnings,
    )
    result["paragraphs"] = paragraphs
    result["blocks"] = blocks
    return result
