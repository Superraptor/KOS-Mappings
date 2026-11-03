import json
import logging
import sys
import subprocess
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------
# Optional imports – they are only required for the new capabilities.
# ----------------------------------------------------------------------
try:
    import textract                     # for .doc (binary) files
except Exception:
    textract = None

try:
    from pdf2image import convert_from_path   # OCR on image‑only PDFs
except Exception:
    convert_from_path = None

try:
    import pytesseract                        # OCR engine
except Exception:
    pytesseract = None

import pdfplumber

# ----------------------------------------------------------------------
# Helper: turn a raw 2‑D matrix (list‑of‑lists) into the unified JSON format
# ----------------------------------------------------------------------
def matrix_to_json(matrix):
    """Normalise a raw matrix to {"headers": [...], "rows": [{...}, ...]}."""
    # Drop completely empty rows
    cleaned = [r for r in matrix if any(c not in (None, "") for c in r)]
    if not cleaned:
        return {"headers": [], "rows": []}

    # First row is a header if any cell is non‑empty
    header_row = cleaned[0]
    has_header = any(c not in (None, "") for c in header_row)

    if has_header:
        headers = [
            f"col_{i+1}" if (c is None or c == "") else str(c).strip()
            for i, c in enumerate(header_row)
        ]
        data = cleaned[1:]
    else:
        col_cnt = max(len(r) for r in cleaned)
        headers = [f"col_{i+1}" for i in range(col_cnt)]
        data = cleaned

    rows = []
    for r in data:
        padded = r + [""] * (len(headers) - len(r))
        rows.append({h: (c if c is not None else "") for h, c in zip(headers, padded)})

    return {"headers": headers, "rows": rows}


# ----------------------------------------------------------------------
# ----------------------------------------------------- DOC / DOCX
# ----------------------------------------------------------------------
def extract_tables_from_docx(path: Path) -> list[dict]:
    """Extract tables from a .docx using python‑docx."""
    from docx import Document

    logging.info("Processing DOCX: %s", path)
    doc = Document(path)
    out = []
    for idx, table in enumerate(doc.tables, start=1):
        raw = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        json_tbl = matrix_to_json(raw)
        json_tbl["source"] = f"{path.name} – table {idx}"
        out.append(json_tbl)
    return out


def convert_doc_to_docx(doc_path: Path) -> Path | None:
    """
    Try to convert a legacy .doc to .docx using LibreOffice in headless mode.
    Returns the path to the new .docx or None if conversion fails.
    """
    try:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "docx", "--outdir", str(Path.cwd()), str(doc_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        new_name = doc_path.with_suffix(".docx").name
        new_path = Path.cwd() / new_name
        if new_path.is_file():
            logging.debug("Converted %s → %s", doc_path, new_path)
            return new_path
    except Exception as e:
        logging.debug("LibreOffice conversion failed: %s", e)
    return None


def extract_tables_from_legacy_doc(path: Path) -> list[dict]:
    """
    Handle old binary .doc files.
    Strategy:
      1️⃣ Try LibreOffice conversion to .docx and then reuse the .docx extractor.
      2️⃣ If conversion fails, fall back to textract → plain‑text → heuristic table parse.
    """
    logging.info("Processing legacy .doc: %s", path)

    # 1️⃣ Attempt conversion
    converted = convert_doc_to_docx(path)
    if converted:
        return extract_tables_from_docx(converted)

    # 2️⃣ Fallback: textract (requires antiword)
    if textract:
        try:
            raw_bytes = textract.process(str(path))
            text = raw_bytes.decode(errors="ignore")
            # Very naive table detection – split on newlines and on tabs/multiple spaces
            raw_matrix = [
                [cell for cell in line.split("\t") if cell] or line.split()
                for line in text.splitlines()
                if line.strip()
            ]
            json_tbl = matrix_to_json(raw_matrix)
            json_tbl["source"] = f"{path.name} – extracted via textract"
            return [json_tbl]
        except Exception as e:
            logging.warning("textract failed for %s: %s", path, e)

    # If everything fails, return empty list
    logging.warning("Could not extract tables from .doc: %s", path)
    return []


# ----------------------------------------------------------------------
# --------------------------------------------------- PDF (searchable)
# ----------------------------------------------------------------------
def extract_tables_from_searchable_pdf(pdf_path: Path) -> list[dict]:
    """Extract tables from a normal, text‑based PDF using pdfplumber."""
    logging.info("Processing searchable PDF: %s", pdf_path)
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            raw_tables = page.extract_tables()
            logging.debug("Page %d – %d raw tables", page_no, len(raw_tables))
            for idx, raw in enumerate(raw_tables, start=1):
                tbl = matrix_to_json(raw)
                tbl["source"] = f"{pdf_path.name} – page {page_no} – table {idx}"
                tables.append(tbl)
    return tables


# ----------------------------------------------------------------------
# --------------------------------------------------- PDF (image‑only) – OCR path
# ----------------------------------------------------------------------
def extract_tables_from_image_pdf(pdf_path: Path) -> list[dict]:
    """
    Perform OCR on each page of a scanned PDF, then run a *very* simple
    table parser on the resulting text.
    """
    if not (convert_from_path and pytesseract):
        raise RuntimeError(
            "OCR dependencies missing – install `pdf2image` and `pytesseract`."
        )

    logging.info("Running OCR on image‑only PDF: %s", pdf_path)

    # Convert PDF pages to PIL images (default DPI 300 gives decent OCR)
    images = convert_from_path(str(pdf_path), dpi=300)
    tables = []

    for page_no, img in enumerate(images, start=1):
        # OCR the whole page as a string; we rely on whitespace to separate columns
        ocr_text = pytesseract.image_to_string(img)
        # Split into rows based on line breaks, then cells on multiple spaces or tabs
        raw = [
            [cell for cell in line.split("\t") if cell] or [c for c in line.split("  ") if c]
            for line in ocr_text.splitlines()
            if line.strip()
        ]
        if raw:
            tbl = matrix_to_json(raw)
            tbl["source"] = f"{pdf_path.name} – OCR page {page_no}"
            tables.append(tbl)

    return tables


# ----------------------------------------------------------------------
# --------------------------------------------------- Unified PDF dispatcher
# ----------------------------------------------------------------------
def extract_tables_from_pdf(pdf_path: Path) -> list[dict]:
    """
    Try the normal pdfplumber extraction first.
    If it yields *no* tables (or only empty cells), fall back to OCR.
    """
    normal = extract_tables_from_searchable_pdf(pdf_path)

    # Heuristic: if we got at least one table with a header, we assume success
    has_real_table = any(t["rows"] for t in normal)
    if has_real_table:
        return normal

    logging.info("No searchable tables found – falling back to OCR.")
    try:
        ocr_tables = extract_tables_from_image_pdf(pdf_path)
        return ocr_tables
    except Exception as e:
        logging.error("OCR fallback failed: %s", e)
        return normal  # return whatever we got (likely empty)


# ----------------------------------------------------------------------
# --------------------------------------------------- Remote handling (download / HTML embed)
# ----------------------------------------------------------------------
def download_remote_file(url: str) -> Path:
    logging.info("Downloading %s", url)
    r = requests.get(url, stream=True, timeout=30)
    r.raise_for_status()
    parsed = urlparse(url)
    name = Path(parsed.path).name or "downloaded"
    out_path = Path.cwd() / name
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return out_path


def find_embedded_doc_url(html_url: str) -> str | None:
    """Search an HTML page for the first embed/iframe/a that points to .pdf, .docx or .doc."""
    resp = requests.get(html_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    for sel in ["embed[src]", "iframe[src]", "a[href]"]:
        for tag in soup.select(sel):
            attr = "src" if tag.name != "a" else "href"
            link = tag.get(attr, "")
            if link.lower().endswith((".pdf", ".docx", ".doc")):
                return urljoin(html_url, link)
    return None


def extract_tables_from_source(source: str) -> list[dict]:
    """Dispatch based on type (URL vs local, file extension)."""
    # URL case
    if source.startswith(("http://", "https://")):
        parsed = urlparse(source)
        suffix = Path(parsed.path).suffix.lower()

        if suffix in (".pdf", ".docx", ".doc"):
            local_path = download_remote_file(source)
            return extract_tables_from_source(str(local_path))

        # HTML page – hunt for an embedded doc
        embed = find_embedded_doc_url(source)
        if embed:
            logging.info("Embedded document discovered: %s", embed)
            return extract_tables_from_source(embed)

        raise ValueError("URL does not point to a supported document and no embed found.")

    # Local file case
    p = Path(source)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {source}")

    ext = p.suffix.lower()
    if ext == ".pdf":
        return extract_tables_from_pdf(p)
    if ext == ".docx":
        return extract_tables_from_docx(p)
    if ext == ".doc":
        return extract_tables_from_legacy_doc(p)
    raise ValueError(f"Unsupported file extension: {ext}")


# ----------------------------------------------------------------------
# --------------------------------------------------- DOCX wrapper (unchanged)
# ----------------------------------------------------------------------
def extract_tables_from_docx(docx_path: Path) -> list[dict]:
    from docx import Document

    logging.info("Processing DOCX: %s", docx_path)
    doc = Document(docx_path)
    out = []
    for idx, table in enumerate(doc.tables, start=1):
        raw = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        tbl = matrix_to_json(raw)
        tbl["source"] = f"{docx_path.name} – table {idx}"
        out.append(tbl)
    return out


# ----------------------------------------------------------------------
# --------------------------------------------------- CLI entry point
# ----------------------------------------------------------------------
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Extract tables from PDF, DOCX, and legacy DOC files (including OCR for scanned PDFs)."
        )
    )
    parser.add_argument("source", help="Path or URL to a document.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        tables = extract_tables_from_source(args.source)
        print(json.dumps(tables, indent=2, ensure_ascii=False))
    except Exception as e:
        logging.error("Failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()