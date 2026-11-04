#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ingest_sssom_archive.py
-----------------------
Ingests SSSOM TSV files from a compressed tar archive (e.g. sssom.tgz)
into the canonical ./commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv structure.
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import re
import sys
import tarfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure repository root and src directory are on sys.path
_SRC_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SRC_DIR.parent
for d in [str(_SRC_DIR), str(_ROOT_DIR)]:
    if d not in sys.path:
        sys.path.insert(0, d)

from src.write_sssom_file import (
    CANONICAL_COLUMN_ORDER,
    MANDATORY_COLUMNS,
    STANDARD_PREFIX_MAP,
    KNOWN_SOURCE_VERSIONS,
    _filter_curie_map,
    _infer_prefix_pair,
    _merge_headers,
    _merge_rows,
    _read_sssom_tsv,
    _resolve_structure_metadata,
    _write_sssom_tsv,
)

if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LOGGER = logging.getLogger(__name__)


def _parse_sssom_stream(
    stream: io.BufferedReader,
    filename: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Parses an SSSOM TSV file from a byte stream.
    Returns (metadata, cross_ontology_rows).
    """
    metadata: Dict[str, Any] = {}
    curie_map: Dict[str, str] = {}
    data_lines: List[str] = []
    in_curie_map = False

    for line_bytes in stream:
        line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            continue
        if line.startswith("#"):
            comment = line.lstrip("#").strip()
            if comment.startswith("curie_map:"):
                in_curie_map = True
                continue
            if in_curie_map:
                if ":" in comment:
                    pfx, ns = comment.split(":", 1)
                    pfx_clean = pfx.strip().strip("'\"")
                    ns_clean = ns.strip().strip("'\"")
                    if pfx_clean and ns_clean:
                        curie_map[pfx_clean] = ns_clean
                    continue
                else:
                    in_curie_map = False
            if ":" in comment:
                k, v = comment.split(":", 1)
                k_clean = k.strip().strip("'\"")
                v_clean = v.strip().strip("'\"")
                if k_clean and v_clean and k_clean != "curie_map":
                    metadata[k_clean] = v_clean
        else:
            data_lines.append(line)

    if curie_map:
        metadata["curie_map"] = curie_map

    if not data_lines:
        return metadata, []

    reader = csv.DictReader(data_lines, delimiter="\t")
    cross_rows: List[Dict[str, Any]] = []

    file_tool = metadata.get("mapping_tool", "OLS SSSOM Pipeline")
    file_provider = metadata.get("mapping_provider", f"https://www.ebi.ac.uk/ols4")
    file_confidence = metadata.get("mapping_set_confidence", "0.7")
    file_license = metadata.get("license") or "https://w3id.org/sssom/license/unspecified"

    if metadata.get("mapping_date") and str(metadata["mapping_date"]).startswith("2026-11"):
        del metadata["mapping_date"]
    if metadata.get("mapping_set_version") and str(metadata["mapping_set_version"]).startswith("2026-11"):
        del metadata["mapping_set_version"]

    for r in reader:
        s_id = str(r.get("subject_id", "")).strip()
        o_id = str(r.get("object_id", "")).strip()
        pred = str(r.get("predicate_id", "")).strip()
        if not s_id or not o_id or ":" not in s_id or ":" not in o_id:
            continue

        # Normalize CURIE prefixes (lowercase)
        s_parts = s_id.split(":", 1)
        o_parts = o_id.split(":", 1)
        s_pfx = s_parts[0].lower()
        o_pfx = o_parts[0].lower()

        # Skip internal ontology hierarchy triples
        if s_pfx == o_pfx:
            continue

        norm_s_id = f"{s_pfx}:{s_parts[1]}"
        norm_o_id = f"{o_pfx}:{o_parts[1]}"

        row_dict = dict(r)
        row_dict["subject_id"] = norm_s_id
        row_dict["object_id"] = norm_o_id
        row_dict["subject_source"] = s_pfx
        row_dict["object_source"] = o_pfx
        if not row_dict.get("mapping_justification"):
            row_dict["mapping_justification"] = "semapv:UnspecifiedMatching"
        if not row_dict.get("mapping_tool"):
            row_dict["mapping_tool"] = file_tool
        if not row_dict.get("mapping_provider"):
            row_dict["mapping_provider"] = file_provider
        
        row_m_date = str(row_dict.get("mapping_date", "")).strip()
        if row_m_date and not row_m_date.startswith("2026-11"):
            row_dict["mapping_date"] = row_m_date
        else:
            row_dict["mapping_date"] = ""

        if not row_dict.get("confidence") and file_confidence:
            row_dict["confidence"] = file_confidence
        if not row_dict.get("license"):
            row_dict["license"] = file_license

        # Versions
        if s_pfx in KNOWN_SOURCE_VERSIONS and not row_dict.get("subject_source_version"):
            row_dict["subject_source_version"] = KNOWN_SOURCE_VERSIONS[s_pfx]
        if o_pfx in KNOWN_SOURCE_VERSIONS and not row_dict.get("object_source_version"):
            row_dict["object_source_version"] = KNOWN_SOURCE_VERSIONS[o_pfx]

        cross_rows.append(row_dict)

    return metadata, cross_rows


def ingest_archive(
    archive_path: Path,
    *,
    max_files: Optional[int] = None,
    max_file_size_mb: float = 25.0,
    file_filter: Optional[str] = None,
    prefix_filter: Optional[str] = None,
) -> Dict[str, int]:
    """
    Ingest SSSOM files from tar archive.
    Returns stats mapping pair -> count of rows written/merged.
    """
    commons_root = _ROOT_DIR / "commons"
    stats: Dict[str, int] = defaultdict(int)
    files_processed = 0

    with tarfile.open(archive_path, "r:*") as tar:
        LOGGER.info("Streaming archive members...")
        for m in tar:
            if not m.name.endswith(".tsv"):
                continue
            fname = m.name.split("/")[-1]
            if file_filter and file_filter.lower() not in fname.lower():
                continue

            size_mb = m.size / (1024 * 1024)
            if size_mb > max_file_size_mb:
                continue

            if max_files and files_processed >= max_files:
                LOGGER.info("Reached file limit of %d mapped files.", max_files)
                break

            stream = tar.extractfile(m)
            if not stream:
                continue

            meta, rows = _parse_sssom_stream(stream, fname)
            if not rows:
                continue

            files_processed += 1
            LOGGER.info("[%d] Ingested %s (%.2f MB, %d cross-ontology rows)...", files_processed, fname, size_mb, len(rows))

            # Group rows by canonical prefix pair
            groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
            for r in rows:
                p1 = r["subject_source"]
                p2 = r["object_source"]
                if prefix_filter and prefix_filter.lower() not in (p1, p2):
                    continue
                groups[(p1, p2)].append(r)

            LOGGER.info("  Extracted %d cross-ontology rows across %d pair(s)", len(rows), len(groups))

            # Merge into canonical files
            for (p1, p2), group_rows in groups.items():
                canonical_path = commons_root / p1 / p2 / f"{p1}_{p2}.sssom.tsv"
                pair_name = f"{p1}_{p2}"

                group_meta = dict(meta)
                group_meta["mapping_set_id"] = f"https://w3id.org/commons/mappings/{pair_name}"
                group_meta["mapping_set_title"] = f"{p1.upper()} to {p2.upper()} Mappings"
                group_meta["subject_source"] = p1
                group_meta["object_source"] = p2
                if p1 in KNOWN_SOURCE_VERSIONS:
                    group_meta["subject_source_version"] = KNOWN_SOURCE_VERSIONS[p1]
                if p2 in KNOWN_SOURCE_VERSIONS:
                    group_meta["object_source_version"] = KNOWN_SOURCE_VERSIONS[p2]

                if canonical_path.is_file():
                    try:
                        old_meta, old_rows, _ = _read_sssom_tsv(canonical_path)
                        merged_meta = _merge_headers(old_meta, group_meta)
                        merged_rows, fieldnames = _merge_rows(old_rows, group_rows)
                        merged_meta["curie_map"] = _filter_curie_map(
                            merged_meta.get("curie_map"), merged_rows, merged_meta, p1, p2
                        )
                        _write_sssom_tsv(canonical_path, merged_meta, merged_rows, fieldnames)
                        stats[pair_name] += len(group_rows)
                    except Exception as e:
                        LOGGER.warning("Error merging into %s: %s", canonical_path, e)
                else:
                    try:
                        all_cols = set()
                        for r in group_rows:
                            all_cols.update(r.keys())
                        fieldnames = [c for c in CANONICAL_COLUMN_ORDER if c in all_cols or c in MANDATORY_COLUMNS]
                        for c in sorted(all_cols):
                            if c not in fieldnames:
                                fieldnames.append(c)
                        group_meta["curie_map"] = _filter_curie_map(
                            group_meta.get("curie_map"), group_rows, group_meta, p1, p2
                        )
                        _write_sssom_tsv(canonical_path, group_meta, group_rows, fieldnames)
                        stats[pair_name] += len(group_rows)
                    except Exception as e:
                        LOGGER.warning("Error writing %s: %s", canonical_path, e)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest SSSOM archive into commons/.")
    parser.add_argument("--archive", default=r"C:\Users\clair\Downloads\sssom.tgz", help="Path to sssom.tgz")
    parser.add_argument("--max-files", type=int, default=None, help="Max files to process")
    parser.add_argument("--max-file-size-mb", type=float, default=25.0, help="Max individual file size in MB")
    parser.add_argument("--file-filter", help="Filter by archive member filename substring")
    parser.add_argument("--prefix-filter", help="Filter by ontology prefix")
    args = parser.parse_args()

    archive_path = Path(args.archive)
    if not archive_path.exists():
        print(f"Archive not found: {archive_path}")
        sys.exit(1)

    print(f"Ingesting from {archive_path}...")
    stats = ingest_archive(
        archive_path,
        max_files=args.max_files,
        max_file_size_mb=args.max_file_size_mb,
        file_filter=args.file_filter,
        prefix_filter=args.prefix_filter,
    )
    print(f"\nIngested {len(stats)} unique cross-ontology pairs:")
    for pair, count in sorted(stats.items(), key=lambda x: x[1], reverse=True)[:30]:
        print(f"  {pair}: {count} rows")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
