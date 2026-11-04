#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
load_from_spreadsheet.py
------------------------
Utility to ingest Excel (.xls, .xlsx), CSV, and TSV tables into SSSOM format.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import pathlib
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

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
    "icd10cm": "http://hl7.org/fhir/sid/icd-10-cm/",
    "icd9cm": "http://hl7.org/fhir/sid/icd-9-cm/",
    "icd10pcs": "http://www.cms.gov/Medicare/Coding/ICD10/",
    "icd9pcs": "http://hl7.org/fhir/sid/icd-9-proc/",
    "icd10": "http://id.who.int/icd/release/10/",
    "icd11": "http://id.who.int/icd/release/11/mms/",
    "isbn": "urn:isbn:",
    "issn": "urn:issn:",
    "ebsco": "https://www.ebsco.com/mid/",
}


def _is_url(candidate: str) -> bool:
    return candidate.startswith(("http://", "https://"))


_UNNAMED_RE = re.compile(r"^Unnamed:\s*\d+$", re.I)


def _is_unnamed(value: Any) -> bool:
    return isinstance(value, str) and bool(_UNNAMED_RE.match(value.strip()))


def _detect_excel_header(
    df: pd.DataFrame,
    min_non_null: int = 2,
) -> Optional[int]:
    """
    Scan a DataFrame read with header=None and locate the true column header row.
    Finds the first row within the first 35 rows having at least 3 clean text columns
    that do not look like section headers or data rows.
    """
    max_scan = min(35, len(df))
    for idx in range(max_scan):
        row = df.iloc[idx]
        strings = [
            str(v).strip() for v in row.dropna()
            if isinstance(v, str) and str(v).strip() and not _is_unnamed(str(v).strip())
        ]
        # Ignore rows that begin with section markers (e.g. 'A. From ...', 'B. Properties ...')
        if any(re.match(r"^[A-Z]\.\s+", s) for s in strings):
            continue
        # Ignore long prose descriptions (e.g., notes/disclaimers)
        valid_cols = [s for s in strings if len(s) < 80 and not s.startswith('"')]
        if len(valid_cols) >= max(3, min_non_null):
            LOGGER.debug("Excel header detected at row %s (%d text columns)", idx, len(valid_cols))
            return idx

    # Fallback: scan for row with highest count of non-section valid strings
    best_idx = 0
    best_count = 0
    for idx in range(max_scan):
        row = df.iloc[idx]
        strings = [
            str(v).strip() for v in row.dropna()
            if isinstance(v, str) and str(v).strip() and not _is_unnamed(str(v).strip())
            and not re.match(r"^[A-Z]\.\s+", str(v).strip())
        ]
        valid = [s for s in strings if len(s) < 80]
        if len(valid) > best_count:
            best_count = len(valid)
            best_idx = idx

    return best_idx


def _read_excel(
    source: Union[pathlib.Path, io.BytesIO],
    sheet_name: Union[str, int] = 0,
    min_non_null: int = 2,
) -> pd.DataFrame:
    raw = pd.read_excel(
        source,
        sheet_name=sheet_name,
        header=None,
        dtype=object,
    )
    header_idx = _detect_excel_header(raw, min_non_null=min_non_null)
    if header_idx is None:
        LOGGER.warning("Could not locate clean header row, using row 0.")
        header_idx = 0

    header_row = raw.iloc[header_idx].astype(str).str.strip()
    data = raw.iloc[header_idx + 1 :].reset_index(drop=True)
    data.columns = [str(c).replace("\n", " ").strip() for c in header_row]
    return data


def _read_excel_from_url(
    url: str,
    sheet_name: Union[str, int],
    min_non_null: int = 2,
) -> pd.DataFrame:
    headers = {"User-Agent": "curl/7.68.0"}
    resp = requests.get(url, headers=headers, stream=True, timeout=60)
    resp.raise_for_status()
    content = io.BytesIO(resp.content)
    return _read_excel(content, sheet_name=sheet_name, min_non_null=min_non_null)


def _read_excel_from_path(
    path: pathlib.Path,
    sheet_name: Union[str, int],
    min_non_null: int = 2,
) -> pd.DataFrame:
    return _read_excel(path, sheet_name=sheet_name, min_non_null=min_non_null)


def _read_delimited(
    source: Union[pathlib.Path, str],
    sep: str,
) -> pd.DataFrame:
    if _is_url(source):
        headers = {"User-Agent": "curl/7.68.0"}
        resp = requests.get(source, headers=headers, timeout=60)
        resp.raise_for_status()
        content = resp.content.decode("utf-8-sig", errors="replace")
        return pd.read_csv(io.StringIO(content), sep=sep, dtype=str, keep_default_na=False)
    else:
        path = pathlib.Path(source)
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            return pd.read_csv(f, sep=sep, dtype=str, keep_default_na=False)


def _normalize_to_sssom_rows(df: pd.DataFrame, source: str = "") -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Convert raw dataframe rows into canonical SSSOM rows."""
    curie_map = dict(DEFAULT_PREFIXES)
    df = df.dropna(how="all").fillna("")
    cols = [str(c).strip() for c in df.columns]
    col_map = {c.lower(): c for c in cols}

    # Already SSSOM formatted?
    if "subject_id" in col_map and "object_id" in col_map:
        mappings = []
        for _, row in df.iterrows():
            d = {k: str(v).strip() for k, v in row.items() if str(v).strip()}
            if not d.get("predicate_id"):
                d["predicate_id"] = "skos:exactMatch"
            if not d.get("mapping_justification"):
                d["mapping_justification"] = "semapv:ManualMappingCuration"
            mappings.append(d)
        return mappings, curie_map

    # ICD-10 / ICD-9 GEM detection (CM and PCS, forward and reverse)
    if ("icd10cm" in col_map or "icd10pcs" in col_map) and ("icd9cm" in col_map or "icd9pcs" in col_map):
        c10 = col_map.get("icd10cm") or col_map.get("icd10pcs")
        c9 = col_map.get("icd9cm") or col_map.get("icd9pcs")
        no_map_col = col_map.get("no_map")
        approx_col = col_map.get("approximate")
        comb_col = col_map.get("combination")

        fname = Path(source).name.lower()
        is_pcs = "pcs" in fname or any(len(str(v).strip()) == 7 for v in df[c10].head(10))
        pfx10 = "icd10pcs" if is_pcs else "icd10cm"
        pfx9 = "icd9pcs" if is_pcs else "icd9cm"

        # Determine direction: is ICD-9 the subject (first column) or is ICD-10 the subject?
        first_col_lower = cols[0].lower() if cols else ""
        icd9_is_subject = "icd9" in first_col_lower or "icd9to" in fname

        sub_col = c9 if icd9_is_subject else c10
        obj_col = c10 if icd9_is_subject else c9
        sub_pfx = pfx9 if icd9_is_subject else pfx10
        obj_pfx = pfx10 if icd9_is_subject else pfx9

        # Precompute target frequency to detect many-to-one
        obj_freq: Dict[str, int] = {}
        for _, row in df.iterrows():
            if no_map_col and str(row[no_map_col]).strip() == "1":
                continue
            v_obj = str(row[obj_col]).strip()
            if v_obj and v_obj != "NoDRG":
                obj_freq[v_obj] = obj_freq.get(v_obj, 0) + 1

        mappings = []
        for _, row in df.iterrows():
            val_sub = str(row[sub_col]).strip()
            val_obj = str(row[obj_col]).strip()
            no_map = str(row[no_map_col]).strip() if no_map_col else "0"
            if not val_sub or not val_obj or val_obj == "NoDRG" or no_map == "1":
                continue

            approx = str(row[approx_col]).strip() if approx_col else "0"
            comb = str(row[comb_col]).strip() if comb_col else "0"

            # Appropriate predicate selection based on CMS GEM flag definitions
            if approx == "0":
                pred = "skos:exactMatch"
            elif comb == "1":
                pred = "skos:narrowMatch" if not icd9_is_subject else "skos:broadMatch"
            elif approx == "1" and comb == "0":
                if obj_freq.get(val_obj, 1) > 1:
                    pred = "skos:broadMatch" if not icd9_is_subject else "skos:narrowMatch"
                else:
                    pred = "skos:closeMatch"
            else:
                pred = "skos:exactMatch"

            m = {
                "subject_id": f"{sub_pfx}:{val_sub}",
                "predicate_id": pred,
                "object_id": f"{obj_pfx}:{val_obj}",
                "mapping_justification": "semapv:ManualMappingCuration",
                "mapping_tool": "CMS GEM Translation Framework",
                "mapping_tool_version": "2018",
                "author_id": "https://www.cms.gov",
                "author_label": "Centers for Medicare & Medicaid Services and CDC",
                "creator_id": "https://www.cms.gov",
                "creator_label": "Centers for Medicare & Medicaid Services and CDC",
                "mapping_date": "2017-10-01",
                "license": "https://creativecommons.org/publicdomain/mark/1.0/",
            }
            # Add extra contextual flag columns
            for col in cols:
                if col not in (sub_col, obj_col):
                    v = str(row[col]).strip()
                    if v:
                        m[col.lower()] = v
            mappings.append(m)
        return mappings, curie_map

    # EBSCO title list detection (Coverage Policy, Source Type, ISSN / ISBN, Publication Name, MID)
    issn_isbn_col = next((c for c in cols if "issn" in c.lower() or "isbn" in c.lower()), None)
    pub_col = next((c for c in cols if "publication" in c.lower() or "title" in c.lower()), None)
    mid_col = next((c for c in cols if c.strip().lower() == "mid"), None)
    if issn_isbn_col and pub_col and mid_col:
        mappings = []
        for _, row in df.iterrows():
            id_val = str(row[issn_isbn_col]).strip()
            pub_val = str(row[pub_col]).strip()
            mid_val = str(row[mid_col]).strip()
            if not id_val or not mid_val or id_val.lower() == "nan" or mid_val.lower() == "nan":
                continue

            clean_id = re.sub(r"[^0-9X-]", "", id_val.upper())
            digits = clean_id.replace("-", "")
            if len(digits) in (10, 13):
                pfx = "isbn"
                sub_id = f"isbn:{clean_id}"
            elif len(digits) in (7, 8):
                pfx = "issn"
                sub_id = f"issn:{clean_id}"
            else:
                pfx = "issn"
                sub_id = f"issn:{clean_id}"

            m = {
                "subject_id": sub_id,
                "subject_label": pub_val,
                "predicate_id": "skos:exactMatch",
                "object_id": f"ebsco:{mid_val}",
                "object_label": pub_val,
                "mapping_justification": "semapv:ManualMappingCuration",
                "mapping_tool": "EBSCO Coverage Crosswalk",
                "mapping_tool_version": "2024",
                "author_id": "https://www.ebsco.com",
                "author_label": "EBSCO Information Services",
                "creator_id": "https://www.ebsco.com",
                "creator_label": "EBSCO Information Services",
                "mapping_date": "2024-01-01",
                "license": "https://www.ebsco.com/company/terms-of-use",
            }
            for col in cols:
                if col not in (issn_isbn_col, pub_col, mid_col):
                    v = str(row[col]).strip()
                    if v and not _is_unnamed(col):
                        m[col.lower().replace(" ", "_").rstrip("*")] = v
            mappings.append(m)
        return mappings, curie_map

    # General tabular mapping (first two non-empty columns as subject and object)
    cand_cols = [
        c for c in cols
        if not _is_unnamed(c)
        and not re.match(r"^[A-Z]\.\s+", str(c).strip())
        and not any(bad in str(c).lower() for bad in ["recommendat", "disclaimer", "note", "section", "part"])
        and df[c].dropna().astype(str).str.strip().ne("").sum() >= 5
    ]
    if len(cand_cols) >= 2:
        c1, c2 = cand_cols[0], cand_cols[1]
        p1 = re.sub(r"[^a-zA-Z0-9]", "", c1.lower()) or "col1"
        p2 = re.sub(r"[^a-zA-Z0-9]", "", c2.lower()) or "col2"
        mappings = []
        for _, row in df.iterrows():
            v1 = str(row[c1]).strip()
            v2 = str(row[c2]).strip()
            if not v1 or not v2:
                continue
            s_id = v1 if ":" in v1 else f"{p1}:{v1}"
            o_id = v2 if ":" in v2 else f"{p2}:{v2}"
            m = {
                "subject_id": s_id,
                "predicate_id": "skos:exactMatch",
                "object_id": o_id,
                "mapping_justification": "semapv:ManualMappingCuration",
            }
            mappings.append(m)
        return mappings, curie_map

    # Fallback: raw records
    raw_mappings = df.to_dict(orient="records")
    return raw_mappings, curie_map


def load(
    source: str,
    sheet_name: Union[str, int] = 0,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Load data from spreadsheet source and return standard SSSOM dict.
    """
    if "rda" in source.lower() and "crosswalk" in source.lower():
        from src.load_from_document import _parse_rda_crosswalk_excel
        return _parse_rda_crosswalk_excel(source)

    min_non_null = kwargs.get("min_non_null", 2)
    clean_source = source.split("?")[0].rstrip("/")
    if clean_source.endswith("/content"):
        clean_source = clean_source[:-8]
    ext = pathlib.Path(clean_source).suffix.lower()
    if not ext:
        lower_source = source.lower()
        if ".xlsx" in lower_source:
            ext = ".xlsx"
        elif ".xls" in lower_source:
            ext = ".xls"
        elif ".csv" in lower_source:
            ext = ".csv"
        elif ".tsv" in lower_source:
            ext = ".tsv"

    if ext in {".xls", ".xlsx"}:
        if _is_url(source):
            df = _read_excel_from_url(source, sheet_name, min_non_null)
        else:
            df = _read_excel_from_path(pathlib.Path(source), sheet_name, min_non_null)
    elif ext in {".csv", ".tsv", ".txt"}:
        sep = {".tsv": "\t", ".txt": "\t"}.get(ext, ",")
        df = _read_delimited(source, sep=sep)
    elif _is_url(source):
        df = _read_delimited(source, sep=",")
    else:
        df = pd.read_csv(source, dtype=str, keep_default_na=False)

    mappings, curie_map = _normalize_to_sssom_rows(df, source=str(source))
    LOGGER.info("Loaded %d mappings from spreadsheet %s", len(mappings), source)
    res: Dict[str, Any] = {
        "curie_map": curie_map,
        "mappings": mappings,
    }
    if mappings:
        first_m = mappings[0]
        s_pfx = first_m.get("subject_id", "").split(":")[0]
        o_pfx = first_m.get("object_id", "").split(":")[0]
        lic = first_m.get("license") or "https://w3id.org/sssom/license/unspecified"
        res["license"] = lic
        if "icd" in s_pfx and "icd" in o_pfx:
            res["subject_source"] = s_pfx
            res["subject_source_version"] = "2018" if "10" in s_pfx else "2017"
            res["object_source"] = o_pfx
            res["object_source_version"] = "2018" if "10" in o_pfx else "2017"
            res["mapping_set_version"] = "2018"
            res["mapping_date"] = "2017-10-01"
            res["publication_date"] = "2017-10-01"
            res["mapping_tool"] = "CMS GEM Translation Framework"
            res["mapping_tool_version"] = "2018"
        elif o_pfx == "ebsco":
            res["object_source"] = "ebsco"
            res["object_source_version"] = "2024"
            res["mapping_set_version"] = "2024"
            res["mapping_date"] = "2024-01-01"
            res["publication_date"] = "2024-01-01"
            res["mapping_tool"] = "EBSCO Coverage Crosswalk"
            res["mapping_tool_version"] = "2024"

    return res


def main() -> None:
    parser = argparse.ArgumentParser(description="Load spreadsheet and emit SSSOM JSON.")
    parser.add_argument("source", help="Path or URL to spreadsheet.")
    parser.add_argument("-o", "--output", help="Output file.")
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