
from pathlib import Path
import pymupdf

from app.core.config import settings


tessdata_path = Path(settings.tesseract_data_path)

if not (tessdata_path / "eng.traineddata").is_file():
    raise FileNotFoundError(
        "English Tesseract language data was not found."
    )


# Create a normal PDF containing test text.
source = pymupdf.open()

page = source.new_page(
    width=595,
    height=842
)

page.insert_text(
    (72, 100),
    "ReceivAI UAE OCR Test",
    fontsize=22
)

page.insert_text(
    (72, 150),
    "Invoice Number: RAI-TEST-1001",
    fontsize=14
)

page.insert_text(
    (72, 185),
    "Total Amount: AED 2500.00",
    fontsize=14
)


# Convert the page into an image.
pixmap = page.get_pixmap(
    matrix=pymupdf.Matrix(2, 2),
    alpha=False
)

image_bytes = pixmap.tobytes("png")

source.close()


# Create a new PDF containing only the page image.
scanned_pdf = pymupdf.open()

image_page = scanned_pdf.new_page(
    width=595,
    height=842
)

image_page.insert_image(
    image_page.rect,
    stream=image_bytes
)

test_file = "ocr_test_scanned.pdf"

scanned_pdf.save(test_file)
scanned_pdf.close()


# Run OCR against the scanned page.
document = pymupdf.open(test_file)

page = document[0]

text_page = page.get_textpage_ocr(
    language="eng",
    dpi=200,
    full=True,
    tessdata=str(tessdata_path)
)

extracted_text = page.get_text(
    "text",
    textpage=text_page
)

document.close()


print("\n========== RECEIVAI OCR TEST ==========\n")
print(extracted_text)

if "RAI-TEST-1001" in extracted_text:
    print("\nSUCCESS: Tesseract OCR is working.")

else:
    print("\nFAILED: Expected invoice text was not recognised.")
