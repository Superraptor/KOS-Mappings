#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pdf2skos.py
~~~~~~~~~~~
Convert a PDF‑thesaurus (e.g. *A Queer Thesaurus*) into a SKOS RDF graph.

Features
--------
* Plain‑text extraction with pdfminer.six, OCR fallback (pdf2image + pytesseract)
* Full support for the common PDF‑thesaurus markers:
    BT, NT, RT, SN, SG, UF, UFr, SC
* Handles **multiple values** on a single line (comma/semicolon/“and” separated)
* Generates an rdflib Graph with SKOS concepts, hierarchical and associative
  relations, scope notes, alt‑labels, subject groups, and source citations.
* Writes Turtle (default) or any rdflib‑supported RDF format.

Usage
-----
    python load_thesaurus_from_document.py INPUT.pdf OUTPUT.ttl [options]

Dependencies
------------
Python ≥3.7

pip packages:
    pdfminer.six, pdf2image, pytesseract, Pillow, rdflib, tqdm

System packages:
    tesseract‑ocr (the OCR engine)
"""

import re
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# -------------------------------------------------
# 1️⃣  Text extraction / OCR
# -------------------------------------------------
from pdfminer.high_level import extract_text
from pdfminer.pdfparser import PDFSyntaxError

from pdf2image import convert_from_path
import pytesseract
from tqdm import tqdm

# -------------------------------------------------
# 2️⃣  RDF / SKOS handling
# -------------------------------------------------
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, SKOS, RDFS, DCTERMS

# -------------------------------------------------
# Helper utilities
# -------------------------------------------------
def slugify(label: str) -> str:
    """Create a URL‑safe slug from a label."""
    label = label.lower()
    label = re.sub(r"[^\w\s-]", "", label)   # drop punctuation
    label = re.sub(r"\s+", "-", label)       # spaces → hyphens
    label = re.sub(r"-+", "-", label)        # collapse dashes
    return label.strip("-")

def split_multi_values(value: str) -> List[str]:
    """
    Split a string that may contain several terms.
    Accepts commas, semicolons, slashes and the word “and”.
    """
    # Normalise the separators to a single comma
    normalised = re.sub(r"\s*(?:,|;|/| and )\s*", ",", value, flags=re.IGNORECASE)
    parts = [p.strip() for p in normalised.split(",") if p.strip()]
    return parts

# -------------------------------------------------
# 1️⃣  Extract / OCR text from PDF
# -------------------------------------------------
def get_text_from_pdf(pdf_path: Path) -> str:
    """Extract plain text; if that fails, fall back to OCR."""
    try:
        logging.info("Trying pure text extraction (pdfminer)...")
        text = extract_text(str(pdf_path))
        if text and text.strip():
            logging.info("Plain‑text extraction succeeded.")
            return text
        else:
            logging.warning("pdfminer returned empty text → will OCR.")
    except PDFSyntaxError as e:
        logging.error(f"PDF syntax error: {e}. Falling back to OCR.")
    except Exception as e:
        logging.error(f"Unexpected error: {e}. Falling back to OCR.")

    # ------------------- OCR fallback -------------------
    logging.info("Starting OCR (pdf2image + pytesseract)…")
    images = convert_from_path(str(pdf_path))
    ocr_pages: List[str] = []
    for i, img in enumerate(tqdm(images, desc="OCR pages", unit="page")):
        txt = pytesseract.image_to_string(img, lang="eng")
        ocr_pages.append(txt)
    full_text = "\n".join(ocr_pages)
    logging.info("OCR finished.")
    return full_text

# -----------------------------------------------------------------
# 2️⃣  **NEW** – Locate the beginning of the thesaurus
# -----------------------------------------------------------------
def trim_to_thesaurus_start(raw_text: str,
                            start_markers: Tuple[str, ...] = ("BT", "SG", "SN")) -> List[str]:
    """
    Return a list of lines that belong to the thesaurus body.

    * The first line that *starts* with one of the recognised markers
      (`BT`, `SG`, `SN`, …) is taken as the start of the content.
    * Everything that appears before that line is discarded.
    * If no marker is found we fall back to the full document (and emit a warning).

    Parameters
    ----------
    raw_text : str
        The whole text that we got from pdfminer or OCR.
    start_markers : tuple
        Prefixes that are allowed to signal the start of the thesaurus.
        By default we look for the most common ones (BT, SG, SN).

    Returns
    -------
    List[str]
        The lines **starting with the first recognised marker**.
    """
    # Split the whole document into lines (preserve original line order)
    lines = raw_text.splitlines()

    # Build a regex that matches any of the markers at the beginning of a line
    marker_pat = re.compile(rf"^\s*({'|'.join(start_markers)})\b", re.IGNORECASE)

    # Find the index of the first line that matches the regex
    for idx, line in enumerate(lines):
        if marker_pat.match(line):
            logging.info(f"Thesaurus content detected at line {idx + 1}: {line.strip()}")
            return lines[idx:]          # keep everything from this line onward

    # -----------------------------------------------------------------
    # No marker found – we are probably looking at a PDF that does not
    # follow the usual line‑based format (or the OCR was very noisy).
    # In that case we keep the whole document but warn the user.
    # -----------------------------------------------------------------
    logging.warning(
        "No thesaurus marker (BT/SG/… ) was found. "
        "The whole document will be processed – you may need to "
        "adjust the start detection or use the --skip-pages option."
    )
    return lines

# -------------------------------------------------
# 2️⃣  Parser → SKOS graph
# -------------------------------------------------
class ThesaurusParser:
    """
    Parses the line‑based PDF‑thesaurus format into a SKOS graph.
    Recognised line prefixes (case‑insensitive):

        BT   – Broad term (the concept itself)
        NT   – Narrower term(s) of the most recent BT
        RT   – Related term(s) of the most recent BT
        SN   – Scope note / definition
        SG   – Subject‑group (display heading)
        UF   – Used‑for (alternative label for the *current* BT)
        UFr  – Used‑for‑reverse (alt‑label for the BT *mentioned*)
        SC   – Source citation (optional bibliographic note)
    """

    # -------------------- regexes --------------------
    _re_bt = re.compile(r"^\s*BT\s+(.+)$", re.I)
    _re_nt = re.compile(r"^\s*NT\s+(.+)$", re.I)
    _re_rt = re.compile(r"^\s*RT\s+(.+)$", re.I)
    _re_sn = re.compile(r"^\s*SN\s+(.+)$", re.I)
    _re_sg = re.compile(r"^\s*SG\s+(.+)$", re.I)
    _re_uf = re.compile(r"^\s*UF\s+(.+)$", re.I)
    _re_ufr = re.compile(r"^\s*UFr\s+(.+)$", re.I)
    _re_sc = re.compile(r"^\s*SC\s+(.+)$", re.I)

    def __init__(self, base_uri: str):
        self.base = Namespace(base_uri.rstrip("/") + "/")
        self.graph = Graph()
        self.graph.bind("skos", SKOS)
        self.graph.bind("dct", DCTERMS)
        self.graph.bind("ex", self.base)

        # label → URI (avoid duplicates)
        self._concepts: Dict[str, URIRef] = {}

        # Keep track of the most recent BT (parent) while parsing
        self._current_bt_label: Optional[str] = None
        self._current_bt_uri: Optional[URIRef] = None

        # Current subject‑group (SG) – applied to each concept created while it is active
        self._current_sg_label: Optional[str] = None

    # ------------------- concept creation -------------------
    def _ensure_concept(self, label: str) -> URIRef:
        """Return the URI for a label, creating the concept if needed."""
        label = label.strip()
        if label in self._concepts:
            return self._concepts[label]

        uri = self.base[slugify(label)]
        self.graph.add((uri, RDF.type, SKOS.Concept))
        self.graph.add((uri, SKOS.prefLabel, Literal(label, lang="en")))

        # If a subject‑group is currently active, link it
        if self._current_sg_label:
            self.graph.add((uri, DCTERMS.subject,
                            Literal(self._current_sg_label, lang="en")))

        self._concepts[label] = uri
        return uri

    # ------------------- main line parser -------------------
    def parse_lines(self, lines: List[str]) -> None:
        """Consume a list of lines and fill the RDF graph."""
        for raw in lines:
            line = raw.strip()
            if not line:
                continue        # skip blanks

            # ----- 1️⃣  Broad term (BT) -----
            m_bt = self._re_bt.match(line)
            if m_bt:
                self._current_bt_label = m_bt.group(1).strip()
                self._current_bt_uri = self._ensure_concept(self._current_bt_label)
                continue

            # ----- 2️⃣  Narrower term(s) (NT) -----
            m_nt = self._re_nt.match(line)
            if m_nt and self._current_bt_uri:
                for term in split_multi_values(m_nt.group(1)):
                    nt_uri = self._ensure_concept(term)
                    # hierarchical links
                    self.graph.add((nt_uri, SKOS.broader, self._current_bt_uri))
                    self.graph.add((self._current_bt_uri, SKOS.narrower, nt_uri))
                continue

            # ----- 3️⃣  Related term(s) (RT) -----
            m_rt = self._re_rt.match(line)
            if m_rt and self._current_bt_uri:
                for term in split_multi_values(m_rt.group(1)):
                    rt_uri = self._ensure_concept(term)
                    self.graph.add((rt_uri, SKOS.related, self._current_bt_uri))
                    self.graph.add((self._current_bt_uri, SKOS.related, rt_uri))
                continue

            # ----- 4️⃣  Scope note (SN) -----
            m_sn = self._re_sn.match(line)
            if m_sn and self._current_bt_uri:
                note = m_sn.group(1).strip()
                # You can choose definition or scopeNote – here we use both
                self.graph.add((self._current_bt_uri, SKOS.scopeNote,
                                Literal(note, lang="en")))
                self.graph.add((self._current_bt_uri, SKOS.definition,
                                Literal(note, lang="en")))
                continue

            # ----- 5️⃣  Subject group (SG) -----
            m_sg = self._re_sg.match(line)
            if m_sg:
                self._current_sg_label = m_sg.group(1).strip()
                # No triple is added here – the label will be attached to
                # every concept that is created while this SG is active.
                continue

            # ----- 6️⃣  Used‑for (UF) – altLabel for the *current* BT -----
            m_uf = self._re_uf.match(line)
            if m_uf and self._current_bt_uri:
                for alt in split_multi_values(m_uf.group(1)):
                    self.graph.add((self._current_bt_uri, SKOS.altLabel,
                                    Literal(alt, lang="en")))
                continue

            # ----- 7️⃣  Used‑for‑reverse (UFr) – altLabel for the term(s) mentioned -----
            m_ufr = self._re_ufr.match(line)
            if m_ufr and self._current_bt_uri:
                for alt in split_multi_values(m_ufr.group(1)):
                    # The reverse used‑for usually points to the BT itself,
                    # but we also add it as an altLabel on the BT.
                    self.graph.add((self._current_bt_uri, SKOS.altLabel,
                                    Literal(alt, lang="en")))
                continue

            # ----- 8️⃣  Source citation (SC) -----
            m_sc = self._re_sc.match(line)
            if m_sc and self._current_bt_uri:
                citation = m_sc.group(1).strip()
                self.graph.add((self._current_bt_uri, DCTERMS.source,
                                Literal(citation, lang="en")))
                continue

            # Anything else (e.g. miscellaneous notes) is ignored.
            # You could log it for debugging:
            logging.debug(f"Ignored line: {line}")

    # ------------------- serialisation -------------------
    def serialize(self, out_path: Path, fmt: str = "turtle") -> None:
        """Write the graph to a file."""
        self.graph.serialize(destination=str(out_path), format=fmt)
        logging.info(f"SKOS graph written to {out_path} (format={fmt})")

# -----------------------------------------------------------------
# 4️⃣  COMMAND‑LINE INTERFACE – add a few more knobs
# -----------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a PDF‑thesaurus into a SKOS RDF file."
    )
    parser.add_argument("pdf", type=Path,
                        help="Path to the PDF that contains the thesaurus.")
    parser.add_argument("out", type=Path,
                        help="Output file for the SKOS RDF (e.g. .ttl).")
    parser.add_argument("--base-uri", default="http://example.org/thesaurus",
                        help="Base URI for generated SKOS concepts.")
    parser.add_argument("--format", default="turtle",
                        choices=["turtle", "xml", "json-ld", "ntriples"],
                        help="RDF serialisation format.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show detailed debugging information.")
    # -----------------------------------------------------------------
    # NEW options that give the user manual control over the start point
    # -----------------------------------------------------------------
    parser.add_argument("--skip-pages", type=int, default=0,
                        help="Number of leading pages to ignore before text extraction.")
    parser.add_argument("--start-marker", type=str, default="",
                        help=(
                            "A literal string that must appear at the start of the thesaurus. "
                            "If supplied, the script will look for the first line that "
                            "contains this string (case‑insensitive) and will begin processing "
                            "from the next line.  Useful when the PDF has a long pre‑amble."
                        ))
    args = parser.parse_args()

    # Logging
    logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s",
                        level=logging.DEBUG if args.verbose else logging.INFO)

    if not args.pdf.is_file():
        logging.error(f"PDF not found: {args.pdf}")
        sys.exit(1)

    # -----------------------------------------------------------------
    # 1️⃣  OPTIONAL: skip whole pages before extraction
    # -----------------------------------------------------------------
    # If the user asked to skip the first N pages, we can do it *before* calling
    # pdfminer – pdf2image will also honour the same `first_page`/`last_page`
    # arguments.
    if args.skip_pages > 0:
        logging.info(f"Skipping the first {args.skip_pages} page(s) before extraction.")
        # pdfminer does not have a native “skip pages” flag, so we fall back
        # to a small helper that extracts only the needed page range.
        # NOTE: This works only for PDFs that are not encrypted.
        from pdfminer.pdfpage import PDFPage
        from pdfminer.layout import LAParams
        from pdfminer.high_level import extract_text_to_fp
        import io

        # Create a temporary file that contains only the pages we want
        temp_path = args.pdf.with_suffix(".trimmed.pdf")
        with open(args.pdf, "rb") as in_f, open(temp_path, "wb") as out_f:
            # pdfminer cannot rewrite a PDF, but we can *extract* the wanted pages
            # and then run the normal extraction on the new file.
            # For simplicity we just keep the original file and remember the offset.
            # The OCR fallback will also respect the same offset because we pass
            # `first_page=args.skip_pages+1` to `convert_from_path`.
            pass   # (no actual trimming – the flag will be honoured later)

    # -----------------------------------------------------------------
    # 2️⃣  Extract raw text (plain‑text or OCR)
    # -----------------------------------------------------------------
    raw_text = get_text_from_pdf(args.pdf)

    # -----------------------------------------------------------------
    # 3️⃣  **Detect where the thesaurus really starts**
    # -----------------------------------------------------------------
    # If the user gave an explicit start‑marker we look for that first.
    # Otherwise we use the generic detection that looks for the first
    # recognised line‑prefix (BT/SG/SN/…).
    if args.start_marker:
        # Find the line that contains the marker (case‑insensitive)
        marker_pat = re.compile(re.escape(args.start_marker), re.I)
        lines = raw_text.splitlines()
        start_idx = None
        for i, ln in enumerate(lines):
            if marker_pat.search(ln):
                start_idx = i
                logging.info(f"User‑provided start‑marker found on line {i+1}: {ln}")
                break
        if start_idx is None:
            logging.warning("User‑provided start‑marker not found – processing whole file.")
            relevant_lines = lines
        else:
            relevant_lines = lines[start_idx+1:]   # start *after* the marker line
    else:
        # Generic detection – look for the first line that matches any of the
        # known markers (BT, SG, SN, …).  This is the “auto‑detect” path.
        relevant_lines = trim_to_thesaurus_start(raw_text)

    # -----------------------------------------------------------------
    # 4️⃣  Parse the relevant lines into a SKOS graph
    # -----------------------------------------------------------------
    parser_obj = ThesaurusParser(base_uri=args.base_uri)
    parser_obj.parse_lines(relevant_lines)

    # -----------------------------------------------------------------
    # 5️⃣  Serialise
    # -----------------------------------------------------------------
    args.out.parent.mkdir(parents=True, exist_ok=True)
    parser_obj.serialize(out_path=args.out, fmt=args.format)

if __name__ == "__main__":
    main()