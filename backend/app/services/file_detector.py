from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile
from io import BytesIO

from app.core.config import settings
from app.services.csv_extractor import extract_csv
from app.services.excel_extractor import extract_excel
from app.services.pdf_extractor import extract_pdf
from app.services.word_extractor import extract_word


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".csv"}
MAX_OFFICE_ARCHIVE_MEMBERS = 2000
MAX_OFFICE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_OFFICE_MEMBER_BYTES = 50 * 1024 * 1024


def detect_file_type(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            "Unsupported file format. Allowed formats: PDF, DOCX, XLSX, XLS and CSV."
        )
    return extension


def _validate_office_archive(
    file_bytes: bytes,
    extension: str,
) -> None:
    if not file_bytes.startswith(b"PK"):
        raise ValueError(f"Invalid {extension[1:].upper()} file signature.")

    try:
        with ZipFile(BytesIO(file_bytes)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_OFFICE_ARCHIVE_MEMBERS:
                raise ValueError("Office document contains too many archive entries.")

            total_uncompressed = 0
            names = set()
            for entry in entries:
                name = entry.filename.replace("\\", "/")
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Office document contains an unsafe archive path.")
                if entry.flag_bits & 0x1:
                    raise ValueError("Encrypted Office documents are not supported.")
                if entry.file_size > MAX_OFFICE_MEMBER_BYTES:
                    raise ValueError("Office document contains an oversized archive entry.")
                total_uncompressed += entry.file_size
                if total_uncompressed > MAX_OFFICE_UNCOMPRESSED_BYTES:
                    raise ValueError("Office document expands beyond the allowed size.")
                if entry.compress_size == 0 and entry.file_size > 0:
                    raise ValueError("Office document has an invalid compressed entry.")
                if entry.compress_size and entry.file_size / entry.compress_size > 1000:
                    raise ValueError("Office document has an unsafe compression ratio.")
                names.add(name)

            required = (
                {"[Content_Types].xml", "word/document.xml"}
                if extension == ".docx"
                else {"[Content_Types].xml", "xl/workbook.xml"}
            )
            if not required.issubset(names):
                raise ValueError(
                    f"Invalid {extension[1:].upper()} document structure."
                )
    except BadZipFile as exc:
        raise ValueError(
            f"Invalid {extension[1:].upper()} document archive."
        ) from exc


def validate_file_signature(file_bytes: bytes, extension: str) -> None:
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    if extension == ".pdf":
        if not file_bytes.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF file signature.")
    elif extension in {".docx", ".xlsx"}:
        _validate_office_archive(file_bytes, extension)
    elif extension == ".xls":
        if not file_bytes.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise ValueError("Invalid XLS file signature.")
    elif extension == ".csv":
        if b"\x00" in file_bytes:
            raise ValueError("CSV file contains invalid binary data.")
        for encoding in ("utf-8-sig", "utf-8", "cp1252"):
            try:
                file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Unsupported CSV text encoding.")


def extract_uploaded_file(file_bytes: bytes, filename: str) -> dict:
    if len(file_bytes) > settings.max_upload_size_mb * 1024 * 1024:
        raise ValueError(
            f"Maximum upload size is {settings.max_upload_size_mb} MB."
        )
    extension = detect_file_type(filename)
    validate_file_signature(file_bytes, extension)

    if extension == ".pdf":
        return extract_pdf(file_bytes, filename)
    if extension == ".docx":
        return extract_word(file_bytes, filename)
    if extension in {".xlsx", ".xls"}:
        return extract_excel(file_bytes, filename)
    if extension == ".csv":
        return extract_csv(file_bytes, filename)
    raise ValueError("Unable to process uploaded file.")
