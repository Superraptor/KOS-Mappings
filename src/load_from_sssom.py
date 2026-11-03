#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
load_from_sssom.py
------------------
Loader for SSSOM TSV files. Extracts SSSOM metadata and mapping rows.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    "obo": "http://purl.obolibrary.org/obo/",
    "bfo": "http://purl.obolibrary.org/obo/BFO_",
    "mesh": "http://id.nlm.nih.gov/mesh/",
    "chebi": "http://purl.obolibrary.org/obo/CHEBI_",
    "hp": "http://purl.obolibrary.org/obo/HP_",
    "mondo": "http://purl.obolibrary.org/obo/MONDO_",
}


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _normalize_source_url(url: str) -> str:
    """Normalize raw GitHub URLs."""
    if "raw.githubusercontent.com" in url and "/refs/heads/" in url:
        url = url.replace("/refs/heads/", "/")
    return url


def _fetch_sssom_text(source: str) -> str:
    if _is_url(source):
        source = _normalize_source_url(source)
        LOGGER.info("Fetching SSSOM file from %s", source)
        headers = {"User-Agent": "curl/7.68.0"}
        resp = requests.get(source, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.content.decode("utf-8-sig", errors="replace")
    else:
        path = Path(source)
        for enc in ["utf-8-sig", "utf-8", "latin-1"]:
            try:
                with open(path, "r", encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


def load(source: str, **kwargs: Any) -> Dict[str, Any]:
    """
    Parse an SSSOM TSV file and return metadata and mapping rows.
    """
    content = _fetch_sssom_text(source)
    lines = content.splitlines()

    curie_map = dict(DEFAULT_PREFIXES)
    meta: Dict[str, Any] = {}
    data_lines = []
    in_curie_map = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            raw_comment = line.lstrip("#")
            comment_content = raw_comment.strip()
            if comment_content.startswith("curie_map:"):
                in_curie_map = True
                continue
            if in_curie_map:
                is_indented = raw_comment.startswith("  ") or raw_comment.startswith("\t")
                if is_indented and ":" in comment_content:
                    parts = comment_content.split(":", 1)
                    pfx = parts[0].strip()
                    ns = parts[1].strip().strip("'\"")
                    if pfx not in ["mapping_set_id", "mapping_set_title", "mapping_set_version", "license", "mapping_date", "mapping_provider"]:
                        curie_map[pfx] = ns
                        continue
                in_curie_map = False

            if ":" in comment_content:
                k, v = comment_content.split(":", 1)
                meta[k.strip()] = v.strip().strip("'\"")
        else:
            in_curie_map = False
            data_lines.append(line)

    if not data_lines:
        LOGGER.warning("No tabular rows found in %s", source)
        return {"curie_map": curie_map, "mappings": [], **meta}

    reader = csv.DictReader(data_lines, delimiter="\t")
    mappings: List[Dict[str, Any]] = []

    for row in reader:
        # Check required columns
        s_id = row.get("subject_id", "").strip()
        p_id = row.get("predicate_id", "").strip()
        o_id = row.get("object_id", "").strip()

        if not s_id or not o_id:
            continue

        clean_row = {k: v for k, v in row.items() if v is not None}
        if not clean_row.get("mapping_justification"):
            clean_row["mapping_justification"] = "semapv:ManualMappingCuration"
        mappings.append(clean_row)

    LOGGER.info("Loaded %d SSSOM mapping rows from %s", len(mappings), source)
    result = {
        "curie_map": curie_map,
        "mappings": mappings,
    }
    result.update(meta)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse SSSOM TSV file and output JSON.")
    parser.add_argument("source", help="Path or URL to SSSOM TSV.")
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