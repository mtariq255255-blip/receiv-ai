
import logging

import pymupdf

from app.core.config import settings
from app.services.extraction_result import build_extraction_result


logger = logging.getLogger(__name__)


def extract_pdf(
    file_bytes: bytes,
    filename: str = "invoice.pdf",
) -> dict:
    if not file_bytes:
        raise ValueError("The uploaded PDF is empty.")
    if not file_bytes.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF file signature.")
    try:
        document = pymupdf.open(
            stream=file_bytes,
            filetype="pdf"
        )
    except Exception as exc:
        raise ValueError("Unable to open the PDF document.") from exc

    try:
        if document.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported.")
        if document.page_count == 0:
            raise ValueError("The PDF contains no pages.")
        if document.page_count > settings.max_pdf_pages:
            raise ValueError(
                f"PDF exceeds the maximum allowed page count of "
                f"{settings.max_pdf_pages}."
            )

        pages = []
        methods = set()
        warnings = []
        for page_number, page in enumerate(document, start=1):
            page_text = page.get_text("text").strip()
            if len(page_text) >= 25:
                methods.add("pymupdf")
            else:
                try:
                    ocr_options = {
                        "language": "eng",
                        "dpi": 200,
                        "full": True,
                    }
                    if settings.tesseract_data_path:
                        ocr_options["tessdata"] = settings.tesseract_data_path
                    text_page = page.get_textpage_ocr(**ocr_options)
                    page_text = page.get_text(
                        "text",
                        textpage=text_page,
                    ).strip()
                    methods.add("tesseract_ocr")
                    if not page_text:
                        warnings.append(
                            f"No readable text on page {page_number}."
                        )
                except Exception as exc:
                    logger.warning(
                        "OCR failed on PDF page %s: %s",
                        page_number,
                        type(exc).__name__,
                    )
                    warnings.append(
                        f"OCR failed on page {page_number}: "
                        f"{type(exc).__name__}"
                    )
                    page_text = ""
            pages.append(f"--- Page {page_number} ---\n{page_text}")

        if not any(page.strip() for page in pages):
            warnings.append("No readable text was extracted from this PDF.")
        if len(methods) > 1:
            extraction_method = "pymupdf_and_tesseract"
        elif "tesseract_ocr" in methods:
            extraction_method = "tesseract_ocr"
        else:
            extraction_method = "pymupdf"

        return build_extraction_result(
            filename=filename,
            file_type="pdf",
            extraction_method=extraction_method,
            text="\n\n".join(pages),
            metadata={
                "page_count": document.page_count,
                "is_encrypted": False,
            },
            warnings=warnings,
        )
    finally:
        document.close()


def extract_pdf_text(file_bytes: bytes) -> dict:
    """Compatibility wrapper for the existing invoice extraction flow."""
    result = extract_pdf(file_bytes)
    return {
        "text": result["text"][:30000],
        "extraction_method": (
            "ocr"
            if result["extraction_method"] == "tesseract_ocr"
            else (
                "mixed"
                if result["extraction_method"] == "pymupdf_and_tesseract"
                else "native_text"
            )
        ),
        "page_count": result["metadata"]["page_count"],
        "warnings": result["warnings"],
    }
