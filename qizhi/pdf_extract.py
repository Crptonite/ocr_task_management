"""Receipt file (PDF / photo) -> plain text, ready for receipt_parser.parse_receipt_text().

1. PDF with a text layer (e.g. exported from a POS system) -> read directly (reuses app.ai.extractor.pdf_text).
2. Scanned PDF (a photo of a hard copy inside a PDF)       -> render pages to images, OCR (Tesseract).
3. PNG / JPG photo of the receipt                          -> OCR (Tesseract).

OCR is optional: it needs pytesseract + the Tesseract program (and pdf2image + poppler for scanned PDFs).
When they are missing the caller gets an ExtractError with install hints, never a crash.
Set TESSERACT_CMD if the Tesseract program is not on PATH.
"""
import io
import os
import re

from app.ai.extractor import pdf_text

MIN_TEXT_CHARS = 40
MONEY = re.compile(r"\d+[.,]\d{2}\b")
MAGIC = ((b"%PDF", "pdf"), (b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"))


class ExtractError(Exception):
    """The file could not be turned into text (message is shown to the user)."""


def sniff_kind(data: bytes) -> str | None:
    """File type from the first bytes, never from the filename."""
    return next((kind for magic, kind in MAGIC if data.startswith(magic)), None)


def _ocr_image(img) -> str:
    try:
        import pytesseract
        from PIL import ImageOps
    except ImportError as e:
        raise ExtractError("OCR is not installed on this server (pytesseract / Tesseract). "
                           "Paste the receipt text instead.") from e
    if os.getenv("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
    img = ImageOps.grayscale(img.convert("RGB"))
    if img.width < 1000:                                    # small photos OCR badly; upscale
        img = img.resize((1000, int(img.height * 1000 / img.width)))
    img = ImageOps.autocontrast(img)
    try:
        return pytesseract.image_to_string(img, config="--psm 6")   # psm 6 = uniform block, keeps receipt rows
    except pytesseract.TesseractNotFoundError as e:
        raise ExtractError("The Tesseract program was not found on this server. "
                           "Paste the receipt text instead.") from e


def _ocr_pdf(data: bytes) -> str:
    try:
        from pdf2image import convert_from_bytes
    except ImportError as e:
        raise ExtractError("Scanned PDFs need pdf2image + poppler, which are not installed. "
                           "Paste the receipt text instead.") from e
    try:
        pages = convert_from_bytes(data, dpi=300, last_page=5)
    except Exception as e:
        raise ExtractError("Could not render the PDF for OCR (is poppler installed?).") from e
    return "\n".join(_ocr_image(p) for p in pages)


def extract_receipt_text(data: bytes) -> dict:
    """Returns {'text': str, 'method': 'pdf-text' | 'pdf-ocr' | 'image-ocr'}."""
    kind = sniff_kind(data)
    if kind == "pdf":
        text = pdf_text(data)
        if text is None:
            raise ExtractError("Could not open the PDF. Is it password-protected or corrupted?")
        if len(text.strip()) >= MIN_TEXT_CHARS and MONEY.search(text):
            return {"text": text.strip(), "method": "pdf-text"}
        return {"text": _ocr_pdf(data).strip(), "method": "pdf-ocr"}       # no usable text layer -> scanned
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise ExtractError("The image could not be read. Upload a clear PNG or JPG.") from e
    return {"text": _ocr_image(img).strip(), "method": "image-ocr"}
