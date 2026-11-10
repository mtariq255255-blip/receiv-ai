from io import BytesIO
from pathlib import Path
from typing import Any
import warnings as python_warnings

import pandas as pd

from app.services.extraction_result import build_extraction_result


MAX_EXCEL_SHEETS = 30
MAX_EXCEL_ROWS_PER_SHEET = 5000
MAX_EXCEL_COLUMNS = 100


def clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _missing_formula_cache_warnings(file_bytes: bytes) -> list[str]:
    try:
        from openpyxl import load_workbook

        formula_book = load_workbook(
            BytesIO(file_bytes),
            read_only=True,
            data_only=False,
            keep_links=False,
        )
        value_book = load_workbook(
            BytesIO(file_bytes),
            read_only=True,
            data_only=True,
            keep_links=False,
        )
        missing = []
        try:
            for sheet_name in formula_book.sheetnames:
                formula_sheet = formula_book[sheet_name]
                value_sheet = value_book[sheet_name]
                max_row = min(
                    formula_sheet.max_row or 0,
                    MAX_EXCEL_ROWS_PER_SHEET + 1,
                )
                max_column = min(
                    formula_sheet.max_column or 0,
                    MAX_EXCEL_COLUMNS,
                )
                for row in formula_sheet.iter_rows(
                    min_row=1,
                    max_row=max_row,
                    min_col=1,
                    max_col=max_column,
                ):
                    for cell in row:
                        if (
                            isinstance(cell.value, str)
                            and cell.value.startswith("=")
                            and value_sheet[cell.coordinate].value is None
                        ):
                            missing.append(
                                f"Worksheet '{sheet_name}' has a formula "
                                f"without a cached result at {cell.coordinate}."
                            )
                            if len(missing) >= 20:
                                return missing
        finally:
            formula_book.close()
            value_book.close()
        return missing
    except Exception:
        return [
            "Could not inspect formula cached values; review workbook formulas."
        ]


def extract_excel(
    file_bytes: bytes,
    filename: str = "invoice.xlsx",
) -> dict:
    if not file_bytes:
        raise ValueError("The Excel file is empty.")

    extension = Path(filename).suffix.lower()
    if extension not in {".xlsx", ".xls"}:
        raise ValueError("Only XLSX and XLS Excel files are supported.")
    engine = "openpyxl" if extension == ".xlsx" else "xlrd"

    try:
        with python_warnings.catch_warnings():
            python_warnings.simplefilter("ignore")
            workbook = pd.ExcelFile(BytesIO(file_bytes), engine=engine)
    except Exception as exc:
        raise ValueError("Unable to read the Excel workbook.") from exc

    try:
        sheet_names = workbook.sheet_names
        if len(sheet_names) > MAX_EXCEL_SHEETS:
            raise ValueError(
                f"Workbook exceeds {MAX_EXCEL_SHEETS} worksheets."
            )

        column_counts = {}
        if extension == ".xlsx":
            from openpyxl import load_workbook

            dimension_book = load_workbook(
                BytesIO(file_bytes),
                read_only=True,
                data_only=True,
                keep_links=False,
            )
            try:
                for sheet_name in sheet_names:
                    column_counts[sheet_name] = (
                        dimension_book[sheet_name].max_column or 0
                    )
            finally:
                dimension_book.close()

        records = []
        tables = []
        text_parts = []
        result_warnings = []
        if extension == ".xlsx":
            result_warnings.extend(
                _missing_formula_cache_warnings(file_bytes)
            )

        for sheet_name in sheet_names:
            if column_counts.get(sheet_name, 0) > MAX_EXCEL_COLUMNS:
                result_warnings.append(
                    f"Worksheet '{sheet_name}' exceeds "
                    f"{MAX_EXCEL_COLUMNS} columns; extra columns were omitted."
                )
            try:
                read_options = {
                    "sheet_name": sheet_name,
                    "dtype": object,
                    "nrows": MAX_EXCEL_ROWS_PER_SHEET + 1,
                }
                if extension == ".xlsx":
                    width = column_counts.get(sheet_name, 0)
                    if width == 0:
                        continue
                    read_options["usecols"] = range(
                        min(width, MAX_EXCEL_COLUMNS + 1)
                    )
                with python_warnings.catch_warnings():
                    python_warnings.simplefilter("ignore")
                    dataframe = pd.read_excel(
                        workbook,
                        **read_options,
                    )
            except Exception as exc:
                result_warnings.append(
                    f"Could not read worksheet '{sheet_name}': "
                    f"{type(exc).__name__}"
                )
                continue

            if dataframe.shape[0] > MAX_EXCEL_ROWS_PER_SHEET:
                result_warnings.append(
                    f"Worksheet '{sheet_name}' exceeds "
                    f"{MAX_EXCEL_ROWS_PER_SHEET} rows; extra rows were omitted."
                )
                dataframe = dataframe.head(MAX_EXCEL_ROWS_PER_SHEET)
            if dataframe.shape[1] > MAX_EXCEL_COLUMNS:
                result_warnings.append(
                    f"Worksheet '{sheet_name}' exceeds "
                    f"{MAX_EXCEL_COLUMNS} columns; extra columns were omitted."
                )
                dataframe = dataframe.iloc[:, :MAX_EXCEL_COLUMNS]
            dataframe.columns = [
                str(column).strip()
                if not pd.isna(column)
                else f"Column_{index + 1}"
                for index, column in enumerate(dataframe.columns)
            ]
            dataframe = dataframe.dropna(how="all")
            if dataframe.empty:
                continue

            sheet_records = []
            for row in dataframe.to_dict(orient="records"):
                cleaned = {
                    str(key): clean_value(value)
                    for key, value in row.items()
                }
                if any(value is not None for value in cleaned.values()):
                    sheet_records.append(cleaned)
            if not sheet_records:
                continue

            records.extend(sheet_records)
            tables.append({
                "sheet_name": sheet_name,
                "columns": list(dataframe.columns),
                "row_count": len(sheet_records),
                "records": sheet_records,
            })
            text_parts.extend([
                f"WORKSHEET: {sheet_name}",
                "COLUMNS: " + ", ".join(map(str, dataframe.columns)),
            ])
            for record in sheet_records:
                text_parts.append(" | ".join(
                    f"{key}: {value}"
                    for key, value in record.items()
                    if value is not None
                ))

        if not tables:
            result_warnings.append(
                "No readable data rows were found in the workbook."
            )

        return build_extraction_result(
            filename=filename,
            file_type=extension.lstrip("."),
            extraction_method=f"pandas_{engine}",
            text="\n".join(text_parts),
            records=records,
            tables=tables,
            metadata={
                "worksheet_names": sheet_names,
                "worksheet_count": len(sheet_names),
                "record_count": len(records),
            },
            warnings=result_warnings,
        )
    finally:
        workbook.close()
