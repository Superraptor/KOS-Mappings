#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
load_from_document.py
---------------------
Loader for complex document formats:
- MARC authority text files (e.g., LCSH-to-MeSH)
- Zip archives containing mapping tables (e.g., WHO ICD-10 to ICD-11)
- DOI resolution to repositories (e.g., Zenodo / RDA crosswalks)
- Office / PDF documents (delegated to load_tables_from_document / load_thesaurus_from_document)
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LOGGER = logging.getLogger(__name__)

DEFAULT_PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "semapv": "https://w3id.org/semapv/vocab/",
    "lcsh": "http://id.loc.gov/authorities/subjects/",
    "mesh": "http://id.nlm.nih.gov/mesh/",
    "icd10": "http://id.who.int/icd/release/10/",
    "icd11": "http://id.who.int/icd/release/11/mms/",
    "schema": "http://schema.org/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "datacite": "http://datacite.org/schema/kernel-4/",
}


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _normalize_source_url(url: str) -> str:
    if "raw.githubusercontent.com" in url and "/refs/heads/" in url:
        url = url.replace("/refs/heads/", "/")
    return url


def _fetch_bytes(source: str) -> Tuple[bytes, str]:
    if _is_url(source):
        source = _normalize_source_url(source)
        LOGGER.info("Fetching bytes from %s", source)
        headers = {"User-Agent": "curl/7.68.0"}
        resp = requests.get(source, headers=headers, timeout=60, allow_redirects=True)
        resp.raise_for_status()
        ext = Path(resp.url.split("?")[0]).suffix.lower()
        return resp.content, ext
    else:
        path = Path(source)
        with open(path, "rb") as f:
            return f.read(), path.suffix.lower()


_MESH_TO_LCSH_INDEX: Optional[Dict[str, str]] = None
_MESH_QUALIFIER_MAP: Optional[Dict[str, str]] = None


def _get_mesh_indexes() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Load MeSH-to-LCSH mapping data to build a term-to-ID index for cross-referencing.
    Caches data locally to downloads/MeSH-to-LCSH-mapping-data.txt.
    """
    global _MESH_TO_LCSH_INDEX, _MESH_QUALIFIER_MAP
    if _MESH_TO_LCSH_INDEX is not None and _MESH_QUALIFIER_MAP is not None:
        return _MESH_TO_LCSH_INDEX, _MESH_QUALIFIER_MAP

    cache_path = Path("downloads/MeSH-to-LCSH-mapping-data.txt")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if not cache_path.exists() or cache_path.stat().st_size < 1000:
        url = "https://raw.githubusercontent.com/galterlibrary/mapping-project/master/MeSH-to-LCSH-mapping-data.txt"
        LOGGER.info("Fetching MeSH-to-LCSH cross-reference data from %s", url)
        try:
            resp = requests.get(url, headers={"User-Agent": "curl/7.68.0"}, timeout=60)
            if resp.status_code == 200 and len(resp.text) > 1000:
                cache_path.write_text(resp.text, encoding="utf-8")
        except Exception as e:
            LOGGER.warning("Could not fetch MeSH-to-LCSH index: %s", e)

    mesh_term_to_id: Dict[str, str] = {}
    if cache_path.exists():
        text = cache_path.read_text(encoding="utf-8", errors="replace")
        for rec in text.split("=LDR"):
            if not rec.strip():
                continue
            mesh_id = None
            terms = []
            for line in rec.splitlines():
                line = line.strip()
                if line.startswith("=035"):
                    m = re.search(r"\(DNLM\)([A-Za-z0-9]+)", line)
                    if m:
                        mesh_id = m.group(1).strip()
                elif line.startswith("=150") or line.startswith("=450"):
                    m = re.search(r"\$a([^$]+)", line)
                    if m:
                        terms.append(m.group(1).strip())
            if mesh_id:
                for t in terms:
                    mesh_term_to_id[t.lower()] = mesh_id

    qualifier_map: Dict[str, str] = {
        "radionuclide imaging": "Q000531",
        "radiography": "Q000530",
        "veterinary": "Q000662",
        "blood": "Q000097",
        "nursing": "Q000451",
        "genetics": "Q000235",
        "pharmacology": "Q000494",
        "drug effects": "Q000187",
        "deficiency": "Q000172",
        "surgery": "Q000601",
        "instrumentation": "Q000295",
        "diagnosis": "Q000175",
        "education": "Q000193",
        "therapeutic use": "Q000627",
        "therapy": "Q000628",
        "classification": "Q000145",
        "drug therapy": "Q000188",
        "metabolism": "Q000378",
        "ultrasonography": "Q000736",
        "ethics": "Q000941",
        "pathogenicity": "Q000472",
        "immunology": "Q000276",
        "transplantation": "Q000637",
        "pathology": "Q000473",
        "psychology": "Q000523",
        "chemistry": "Q000737",
        "poisoning": "Q000506",
        "utilization": "Q000656",
        "etiology": "Q000209",
        "physiology": "Q000502",
        "prevention & control": "Q000517",
        "rehabilitation": "Q000534",
    }

    _MESH_TO_LCSH_INDEX = mesh_term_to_id
    _MESH_QUALIFIER_MAP = qualifier_map
    return _MESH_TO_LCSH_INDEX, _MESH_QUALIFIER_MAP


def _parse_marc_authority(text: str) -> List[Dict[str, Any]]:
    """
    Parse MARC text export containing LCSH to MeSH mappings.
    Cross-references with MeSH-to-LCSH to ensure validity of MeSH identifiers.
    Identifies combinations and assigns skos:narrowMatch, skos:broadMatch, or skos:exactMatch.
    """
    mesh_term_to_id, qualifier_map = _get_mesh_indexes()
    records = text.split("=LDR")
    mappings: List[Dict[str, Any]] = []

    for rec in records:
        if not rec.strip():
            continue

        lcsh_id = None
        lcsh_label = None
        rec_750s: List[str] = []

        for line in rec.splitlines():
            line = line.strip()
            if line.startswith("=010"):
                m = re.search(r"\$a\s*([a-zA-Z0-9\s]+)", line)
                if m:
                    clean_id = m.group(1).strip().replace(" ", "")
                    if re.match(r"^sh\d+$", clean_id):
                        lcsh_id = f"lcsh:{clean_id}"
            elif line.startswith("=150"):
                m = re.search(r"\$a\s*([^$]+)", line)
                if m:
                    lcsh_label = m.group(1).strip()
            elif line.startswith("=750"):
                if line.startswith("=750  \\2") or "DNLM" in line:
                    rec_750s.append(line)

        if not lcsh_id or not rec_750s:
            continue

        is_combination = len(rec_750s) > 1 or any("$8" in l or "$wb" in l for l in rec_750s)

        for line in rec_750s:
            m_0 = re.search(r"\$0\s*\(\s*DNLM\s*\)\s*([A-Za-z0-9]+)", line)
            m_i = re.search(r"\$i([^$]+)", line)
            m_4 = re.search(r"\$4([^$]+)", line)
            m_a = re.search(r"\$a([^$]+)", line)
            m_x = re.search(r"\$x([^$]+)", line)

            main_term = m_a.group(1).strip() if m_a else ""
            sub_term = m_x.group(1).strip() if m_x else ""

            mesh_id = None
            if m_0:
                raw_0 = m_0.group(1).strip()
                if re.match(r"^[DC]\d{6,9}(?:Q\d{6})?$", raw_0):
                    mesh_id = f"mesh:{raw_0}"

            if not mesh_id and main_term:
                found_id = mesh_term_to_id.get(main_term.lower())
                if found_id:
                    if sub_term and sub_term.lower() in qualifier_map:
                        found_id = f"{found_id}{qualifier_map[sub_term.lower()]}"
                    mesh_id = f"mesh:{found_id}"

            if not mesh_id:
                continue

            label_parts = [p for p in [main_term, sub_term] if p]
            mesh_label = " -- ".join(label_parts) if label_parts else None

            # Determine predicate:
            i_rel = m_i.group(1).strip().lower() if m_i else ""
            code_4 = m_4.group(1).strip().upper() if m_4 else ""

            if "broader" in i_rel or code_4 == "BM":
                pred = "skos:broadMatch"
            elif "narrower" in i_rel or code_4 == "NM":
                pred = "skos:narrowMatch"
            elif "related" in i_rel or code_4 == "RM":
                pred = "skos:relatedMatch"
            elif is_combination:
                pred = "skos:narrowMatch"
            else:
                pred = "skos:exactMatch"

            mapping = {
                "subject_id": lcsh_id,
                "predicate_id": pred,
                "object_id": mesh_id,
                "mapping_justification": "semapv:ManualMappingCuration",
                "subject_source": "lcsh",
                "subject_source_version": "2024",
                "object_source": "mesh",
                "object_source_version": "2024",
                "mapping_provider": "https://raw.githubusercontent.com/galterlibrary/mapping-project/master/LCSH-to-MeSH-mapping-data.txt",
                "license": "https://w3id.org/sssom/license/unspecified",
            }
            if lcsh_label:
                mapping["subject_label"] = lcsh_label
            if mesh_label:
                mapping["object_label"] = mesh_label

            mappings.append(mapping)

    LOGGER.info("Parsed %d validated MARC LCSH-to-MeSH mappings", len(mappings))
    return mappings


def _parse_zip_archive(content: bytes) -> List[Dict[str, Any]]:
    """Parse ZIP archives containing mapping tables (such as WHO ICD-10 to ICD-11)."""
    mappings: List[Dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        names = z.namelist()
        LOGGER.info("Examining zip archive contents: %s", names)

        # Prioritize 10To11MapToOneCategory.txt or similar text table
        txt_files = [n for n in names if n.endswith(".txt") and "Map" in n]
        if not txt_files:
            txt_files = [n for n in names if n.endswith((".txt", ".tsv", ".csv"))]

        for fname in txt_files:
            with z.open(fname) as fh:
                try:
                    df = pd.read_csv(fh, sep="\t", dtype=str).fillna("")
                    cols_lower = {str(c).lower(): c for c in df.columns}
                    # Look for icd10 and icd11 columns
                    c10 = cols_lower.get("icd10code")
                    c11 = cols_lower.get("icd11code")
                    t10 = cols_lower.get("icd10title")
                    t11 = cols_lower.get("icd11title")

                    if c10 and c11:
                        for _, row in df.iterrows():
                            v10 = str(row[c10]).strip()
                            v11 = str(row[c11]).strip()
                            if not v10 or not v11:
                                continue
                            m = {
                                "subject_id": f"icd10:{v10}",
                                "predicate_id": "skos:exactMatch",
                                "object_id": f"icd11:{v11}",
                                "mapping_justification": "semapv:ManualMappingCuration",
                            }
                            if t10:
                                m["subject_label"] = str(row[t10]).strip()
                            if t11:
                                m["object_label"] = str(row[t11]).strip()
                            mappings.append(m)
                        if mappings:
                            LOGGER.info("Extracted %d mappings from %s in zip", len(mappings), fname)
                            break
                except Exception as exc:
                    LOGGER.debug("Could not parse %s in zip: %s", fname, exc)

    return mappings


def _resolve_doi(doi_url: str) -> Dict[str, Any]:
    """Resolve DOI URL, identify dataset repository (e.g. Zenodo), and extract mappings."""
    LOGGER.info("Resolving DOI: %s", doi_url)
    headers = {"User-Agent": "curl/7.68.0", "Accept": "application/json, text/html"}
    r = requests.get(doi_url, headers=headers, allow_redirects=True, timeout=60)
    final_url = r.url

    # Check for Zenodo
    if "zenodo.org" in final_url:
        rec_id = final_url.rstrip("/").split("#")[0].split("/")[-1]
        api_url = f"https://zenodo.org/api/records/{rec_id}"
        z_resp = requests.get(api_url, headers=headers, timeout=30)
        if z_resp.status_code == 200:
            z_data = z_resp.json()
            for f in z_data.get("files", []):
                key = f.get("key", "")
                if key.endswith((".xls", ".xlsx", ".csv", ".tsv")):
                    download_url = f.get("links", {}).get("self")
                    if download_url:
                        LOGGER.info("Fetching Zenodo data file: %s", key)
                        from src.load_from_spreadsheet import load as load_sheet
                        sheet_data = load_sheet(download_url)
                        z_lic_dict = z_data.get("metadata", {}).get("license") or {}
                        z_lic_id = z_lic_dict.get("id") if isinstance(z_lic_dict, dict) else str(z_lic_dict)
                        z_license = "https://creativecommons.org/licenses/by/4.0/" if "cc-by" in str(z_lic_id).lower() else (str(z_lic_id) if z_lic_id else "https://w3id.org/sssom/license/unspecified")
                        sheet_data["license"] = z_license
                        for m in sheet_data.get("mappings", []):
                            m["license"] = z_license
                        # Add RDA prefix
                        sheet_data["curie_map"]["rda"] = "http://rdaregistry.info/Elements/"
                        return sheet_data

    # Fallback to webpage extraction
    from src.load_from_webpage import load as load_web
    return load_web(final_url)


def load(source: str, **kwargs: Any) -> Dict[str, Any]:
    """
    Load mappings from documents (MARC text, ZIP archives, DOIs, etc.).
    """
    curie_map = dict(DEFAULT_PREFIXES)

    # DOI handling
    if "doi.org" in source.lower():
        return _resolve_doi(source)

    content, ext = _fetch_bytes(source)

    # Zip handling
    if ext == ".zip" or content.startswith(b"PK\x03\x04"):
        mappings = _parse_zip_archive(content)
        for m in mappings:
            m["license"] = "https://w3id.org/sssom/license/unspecified"
        return {
            "curie_map": curie_map,
            "mappings": mappings,
            "subject_source": "icd10",
            "subject_source_version": "2019",
            "object_source": "icd11",
            "object_source_version": "2024-01",
            "mapping_set_version": "2024-01",
            "license": "https://w3id.org/sssom/license/unspecified",
        }

    # Text / MARC handling
    text = content.decode("utf-8-sig", errors="replace")
    if "=LDR" in text or "=150" in text:
        mappings = _parse_marc_authority(text)
        return {
            "curie_map": curie_map,
            "mappings": mappings,
            "subject_source": "lcsh",
            "subject_source_version": "2024",
            "object_source": "mesh",
            "object_source_version": "2024",
            "mapping_set_version": "2024",
            "license": "https://w3id.org/sssom/license/unspecified",
        }

    # Generic spreadsheet fallback
    from src.load_from_spreadsheet import load as load_sheet
    return load_sheet(source, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract SSSOM mappings from document.")
    parser.add_argument("source", help="URL or path to document.")
    parser.add_argument("-o", "--output", help="Output JSON file.")
    args = parser.parse_args()

    data = load(args.source)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
