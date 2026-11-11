
import logging

import pymupdf

from app.core.config import settings
from app.services.extraction_result import build_extraction_result


logger = logging.getLogger(__name__)


def _get_page_words(page, textpage=None):
    """Return words with positions for local parsing."""

    kwargs = {"sort": True}

    if textpage is not None:
        kwargs["textpage"] = textpage

    words = page.get_text("words", **kwargs)

    return [
        {
            "text": str(word[4]),
            "bbox": [
                round(float(word[i]), 2)
                for i in range(4)
            ],
            "block_no": int(word[5]),
            "line_no": int(word[6]),
            "word_no": int(word[7]),
        }
        for word in words
    ]


def _get_page_lines(page, textpage=None):
    """Preserve line text and bounding boxes."""

    kwargs = {"sort": True}

    if textpage is not None:
        kwargs["textpage"] = textpage

    content = page.get_text("dict", **kwargs)

    lines = []

    for block in content.get("blocks", []):
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])

            text = "".join(
                span.get("text", "")
                for span in spans
            ).strip()

            if not text:
                continue

            lines.append(
                {
                    "text": text,
                    "bbox": [
                        round(float(value), 2)
                        for value in line.get(
                            "bbox", [0, 0, 0, 0]
                        )
                    ],
                }
            )

    lines.sort(
        key=lambda item: (
            item["bbox"][1],
            item["bbox"][0],
        )
    )

    return lines


def _get_page_tables(page):
    """Attempt native PDF table detection."""

    tables = []

    if not hasattr(page, "find_tables"):
        return tables

    try:
        finder = page.find_tables()

        for index, table in enumerate(finder.tables):
            rows = table.extract() or []

            if not rows:
                continue

            tables.append(
                {
                    "table_index": index,
                    "bbox": [
                        round(float(value), 2)
                        for value in table.bbox
                    ],
                    "rows": rows,
                }
            )

    except Exception as exc:
        logger.warning(
            "Native PDF table detection failed: %s",
            type(exc).__name__,
        )

    return tables


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
            filetype="pdf",
        )
    except Exception as exc:
        raise ValueError(
            "Unable to open the PDF document."
        ) from exc

    try:
        if document.is_encrypted:
            raise ValueError(
                "Password-protected PDFs are not supported."
            )

        if document.page_count == 0:
            raise ValueError(
                "The PDF contains no pages."
            )

        if document.page_count > settings.max_pdf_pages:
            raise ValueError(
                "PDF exceeds the maximum allowed "
                "page count."
            )

        pages = []
        layout_pages = []
        methods = set()
        warnings = []

        for page_number, page in enumerate(
            document,
            start=1,
        ):
            textpage = None

            page_text = page.get_text(
                "text",
                sort=True,
            ).strip()

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
                        ocr_options["tessdata"] = (
                            settings.tesseract_data_path
                        )

                    textpage = page.get_textpage_ocr(
                        **ocr_options
                    )

                    page_text = page.get_text(
                        "text",
                        textpage=textpage,
                        sort=True,
                    ).strip()

                    methods.add("tesseract_ocr")

                except Exception as exc:
                    logger.warning(
                        "OCR failed on page %s: %s",
                        page_number,
                        type(exc).__name__,
                    )

                    warnings.append(
                        f"OCR failed on page {page_number}."
                    )

                    page_text = ""

            page_lines = _get_page_lines(
                page,
                textpage=textpage,
            )

            page_words = _get_page_words(
                page,
                textpage=textpage,
            )

            # Native table detection is most useful
            # for PDFs with an embedded text layer.
            page_tables = (
                _get_page_tables(page)
                if textpage is None
                else []
            )

            pages.append(
                f"--- Page {page_number} ---\n"
                f"{page_text}"
            )

            layout_pages.append(
                {
                    "page_number": page_number,
                    "width": round(float(page.rect.width), 2),
                    "height": round(float(page.rect.height), 2),
                    "lines": page_lines,
                    "words": page_words,
                    "tables": page_tables,
                    "ocr_used": textpage is not None,
                }
            )

            if not page_text:
                warnings.append(
                    f"No readable text on page {page_number}."
                )

        if len(methods) > 1:
            extraction_method = (
                "pymupdf_and_tesseract"
            )
        elif "tesseract_ocr" in methods:
            extraction_method = "tesseract_ocr"
        else:
            extraction_method = "pymupdf"

        result = build_extraction_result(
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

        # Preserve existing extraction-result keys.
        # This information is local and is not
        # intended for direct OpenAI submission.
        result["layout_pages"] = layout_pages

        return result

    finally:
        document.close()


def extract_pdf_text(file_bytes: bytes) -> dict:
    """Compatibility wrapper for older routes."""

    result = extract_pdf(file_bytes)

    method = result["extraction_method"]

    if method == "tesseract_ocr":
        compatibility_method = "ocr"
    elif method == "pymupdf_and_tesseract":
        compatibility_method = "mixed"
    else:
        compatibility_method = "native_text"

    return {
        "text": result["text"][:30000],
        "extraction_method": compatibility_method,
        "page_count": result["metadata"]["page_count"],
        "warnings": result["warnings"],
    }
