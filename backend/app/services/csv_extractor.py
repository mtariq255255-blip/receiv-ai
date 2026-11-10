
from io import BytesIO
from pathlib import Path

import pandas as pd

from app.services.extraction_result import build_extraction_result


MAX_CSV_ROWS = 5000
MAX_CSV_COLUMNS = 100


CSV_COLUMN_ALIASES = {
    "invoice_number": [
        "invoice_number", "invoice_no", "invoice number", "invoice no",
        "invoice id", "bill number", "invoice_num", "invoice",
    ],
    "supplier_name": [
        "supplier_name", "supplier", "seller", "company_name", "vendor",
    ],
    "customer_name": [
        "customer_name", "customer", "buyer", "client", "buyer_name",
    ],
    "customer_email": [
        "customer_email", "email", "buyer_email", "client_email",
    ],
    "amount_aed": [
        "amount_aed", "total_aed", "invoice_amount_aed",
    ],
    "amount": [
        "amount", "total", "total_amount", "grand_total", "invoice_amount",
    ],
    "currency": ["currency", "currency_code"],
    "issue_date": ["issue_date", "invoice_date", "date", "dated"],
    "due_date": ["due_date", "payment_due_date"],
    "supply_date": ["supply_date", "date_of_supply"],
    "supplier_trn": ["supplier_trn", "seller_trn", "trn"],
    "customer_trn": ["customer_trn", "buyer_trn"],
    "description": ["description", "item_description", "product", "service"],
    "quantity": ["quantity", "qty"],
    "unit_price_aed": ["unit_price_aed", "unit_price", "rate", "price"],
    "vat_rate": ["vat_rate", "vat_percent", "tax_rate"],
    "vat_amount_aed": ["vat_amount_aed", "vat_amount", "tax_amount"],
    "taxable_value_aed": [
        "taxable_value_aed", "taxable_value", "assessable_value",
    ],
}


COLUMN_ALIASES = {
    "invoice_number": [
        "invoice_number",
        "invoice_no",
        "invoice_num",
        "invoice_id",
        "invoice",
        "bill_no",
        "document_number"
    ],

    "customer_name": [
        "customer_name",
        "customer",
        "client",
        "client_name",
        "company",
        "bill_to"
    ],

    "customer_email": [
        "customer_email",
        "email",
        "client_email"
    ],

    "amount_aed": [
        "amount_aed",
        "total_aed",
        "invoice_amount_aed",
        "amount",
        "total",
        "invoice_amount"
    ],

    "currency": [
        "currency",
        "currency_code"
    ],

    "issue_date": [
        "issue_date",
        "invoice_date",
        "date",
        "issued_on"
    ],

    "due_date": [
        "due_date",
        "payment_due_date",
        "due",
        "payment_date"
    ],

    "notes": [
        "notes",
        "description",
        "remarks"
    ]
}


def normalize_column(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    aliases = {}
    for standard_name, names in CSV_COLUMN_ALIASES.items():
        aliases[normalize_column(standard_name)] = standard_name
        aliases.update({
            normalize_column(alias): standard_name
            for alias in names
        })
    renamed = {
        column: aliases.get(
            normalize_column(column),
            normalize_column(column),
        )
        for column in dataframe.columns
    }
    dataframe = dataframe.rename(columns=renamed)
    return dataframe.loc[:, ~dataframe.columns.duplicated()]


def extract_csv(
    file_bytes: bytes,
    filename: str = "invoices.csv",
) -> dict:
    if not file_bytes:
        raise ValueError("The CSV file is empty.")
    if Path(filename).suffix.lower() != ".csv":
        raise ValueError("Only CSV files are supported.")

    dataframe = None
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            dataframe = pd.read_csv(
                BytesIO(file_bytes),
                encoding=encoding,
                dtype=object,
                nrows=MAX_CSV_ROWS + 1,
                on_bad_lines="error",
            )
            break
        except UnicodeDecodeError as exc:
            last_error = exc
        except Exception as exc:
            raise ValueError("Unable to read the CSV file.") from exc

    if dataframe is None:
        raise ValueError("Unsupported CSV text encoding.") from last_error
    if len(dataframe) > MAX_CSV_ROWS:
        raise ValueError(
            f"CSV exceeds the maximum of {MAX_CSV_ROWS} rows."
        )
    if len(dataframe.columns) > MAX_CSV_COLUMNS:
        raise ValueError(
            f"CSV exceeds the maximum of {MAX_CSV_COLUMNS} columns."
        )

    dataframe = normalize_columns(dataframe)
    records = []
    for row in dataframe.to_dict(orient="records"):
        cleaned = {}
        for key, value in row.items():
            if pd.isna(value):
                cleaned[key] = None
            elif hasattr(value, "isoformat"):
                cleaned[key] = value.isoformat()
            elif hasattr(value, "item"):
                cleaned[key] = value.item()
            else:
                cleaned[key] = value
        if any(value is not None for value in cleaned.values()):
            records.append(cleaned)

    warnings = []
    if not records:
        warnings.append("No invoice records were found.")
    if "currency" not in dataframe.columns:
        warnings.append(
            "Currency column is missing. Do not assume the amount is AED "
            "without review."
        )
    elif "amount" in dataframe.columns and dataframe["currency"].map(
        lambda value: str(value).strip().upper()
        not in {"AED", "UAE DIRHAM", "UAE DIRHAMS", "د.إ"}
    ).any():
        warnings.append(
            "One or more rows use a non-AED or unrecognized currency. "
            "Do not treat their amounts as AED."
        )
    if "invoice_number" not in dataframe.columns:
        warnings.append("Invoice number column was not identified.")
    if "customer_name" not in dataframe.columns:
        warnings.append("Customer name column was not identified.")

    text_parts = [
        "CSV COLUMNS: " + ", ".join(map(str, dataframe.columns))
    ]
    for index, record in enumerate(records, start=1):
        text_parts.append(
            f"RECORD {index}: "
            + " | ".join(
                f"{key}: {value}"
                for key, value in record.items()
                if value is not None
            )
        )

    return build_extraction_result(
        filename=filename,
        file_type="csv",
        extraction_method="pandas",
        text="\n".join(text_parts),
        records=records,
        tables=[{
            "table_number": 1,
            "columns": list(dataframe.columns),
            "row_count": len(records),
        }],
        metadata={
            "row_count": len(records),
            "column_count": len(dataframe.columns),
            "columns": list(dataframe.columns),
        },
        warnings=warnings,
    )


def normalise_header(header: str) -> str:
    """Convert CSV column names to comparable values."""

    return (
        str(header)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def extract_csv_rows(file_bytes: bytes) -> list[dict]:
    """Extract invoice records from a CSV file."""

    dataframe = None
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            dataframe = pd.read_csv(
                BytesIO(file_bytes),
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
                nrows=501,
            )
            break
        except UnicodeDecodeError as exc:
            last_error = exc
        except Exception as exc:
            raise ValueError(
                "Unable to read the CSV file. "
                "Please check its encoding and structure."
            ) from exc

    if dataframe is None:
        raise ValueError("Unsupported CSV text encoding.") from last_error

    if dataframe.empty:
        raise ValueError("The CSV file contains no invoice records.")

    if len(dataframe) > 500:
        raise ValueError(
            "A maximum of 500 invoice rows is supported per CSV upload."
        )
    if len(dataframe.columns) > MAX_CSV_COLUMNS:
        raise ValueError(
            f"CSV exceeds the maximum of {MAX_CSV_COLUMNS} columns."
        )

    dataframe.columns = [
        normalise_header(column)
        for column in dataframe.columns
    ]

    # Locate source columns using aliases.
    column_mapping = {}

    for target_field, aliases in COLUMN_ALIASES.items():

        for alias in aliases:

            if alias in dataframe.columns:
                column_mapping[target_field] = alias
                break

    required_columns = [
        "invoice_number",
        "customer_name",
        "amount_aed",
        "issue_date",
        "due_date"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in column_mapping
    ]

    if missing_columns:
        raise ValueError(
            "CSV is missing required columns: "
            + ", ".join(missing_columns)
        )

    results = []

    for index, row in dataframe.iterrows():

        fields = {}

        for target_field in COLUMN_ALIASES:

            source_column = column_mapping.get(target_field)

            value = (
                row[source_column]
                if source_column
                else None
            )

            if value is not None:
                value = str(value).strip()

            fields[target_field] = value or None

        notes = []

        amount_column = column_mapping.get("amount_aed")
        amount_explicitly_aed = bool(
            amount_column
            and normalise_header(amount_column).endswith("_aed")
        )
        currency = str(fields.get("currency") or "").strip().upper()
        if currency not in ("AED", "UAE DIRHAM", "UAE DIRHAMS", "د.إ"):
            if currency:
                fields["amount_aed"] = None
                notes.append(
                    "The CSV amount is not clearly denominated in AED. "
                    "Enter an AED amount only after administrator review."
                )
            elif amount_explicitly_aed:
                notes.append(
                    "Currency is missing; the amount was retained only "
                    "because its column is explicitly labelled AED."
                )
            else:
                fields["amount_aed"] = None
                notes.append(
                    "Currency was not provided in the CSV. Do not assume "
                    "the amount is AED without review."
                )

        results.append({
            "record_index": int(index) + 1,
            "fields": fields,
            "confidence": 0.99,
            "notes": notes,
            "source_format": "csv"
        })

    return results
