#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
src/manual_sssom_input.py

Interactively build a small SSSOM mapping file.

The user is prompted for:

* **Metadata** – the comment lines that usually appear at the top of an
  SSSOM file (e.g. `mapping_set_id`, `mapping_set_version`,
  `curation_source`, …).  Any key/value pair can be entered; pressing
  **Enter** on an empty key finishes the metadata section.

* **Mappings** – one or more rows containing at least the three required
  columns `subject_id`, `predicate_id`, `object_id`.  The user can add
  any additional columns they wish (e.g. `confidence`, `mapping_tool`,
  …).  After each row the user is asked whether to add another row.

When the user is done the script writes a valid SSSOM TSV file that looks
like:

    # key1: value1
    # key2: value2
    subject_id    predicate_id    object_id    <extra columns …>
    CURIE:001     skos:exactMatch CURIE:ABC    …

The file is written to the current working directory with the name
provided by the user (default: ``manual.sssom.tsv``).

Usage
-----
    $ python src/manual_sssom_input.py          # interactive
    $ python src/manual_sssom_input.py -o myfile.tsv
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def _prompt(message: str, default: str | None = None) -> str:
    """Simple wrapper around ``input`` that shows a default value."""
    if default is not None:
        prompt = f"{message} [{default}]: "
    else:
        prompt = f"{message}: "
    answer = input(prompt).strip()
    return answer if answer else (default or "")


def _collect_metadata() -> Dict[str, str]:
    """
    Ask the user for arbitrary metadata key/value pairs.
    The loop stops when the user enters an empty key.
    """
    print("\n=== METADATA INPUT ===")
    print(
        "Enter metadata as key/value pairs (e.g. mapping_set_id, version, "
        "curation_source, etc.).  Press **Enter** on an empty key when you "
        "are finished.\n"
    )
    metadata: Dict[str, str] = {}
    while True:
        key = input("Metadata key (blank to finish): ").strip()
        if not key:
            break
        value = input(f"  Value for '{key}': ").strip()
        metadata[key] = value
    return metadata


def _collect_one_mapping(extra_columns: List[str]) -> Dict[str, str]:
    """
    Prompt the user for a single mapping row.  The required columns are
    ``subject_id``, ``predicate_id`` and ``object_id``.  Any extra columns
    that were previously defined are also asked for.
    """
    print("\n--- New mapping row ---")
    row: Dict[str, str] = {}
    row["subject_id"] = _prompt("  subject_id (e.g. CURIE:123)")
    row["predicate_id"] = _prompt("  predicate_id (e.g. skos:exactMatch)")
    row["object_id"] = _prompt("  object_id (e.g. CURIE:XYZ)")

    # Ask for any extra columns the user wants to include
    for col in extra_columns:
        val = _prompt(f"  {col} (optional)", "")
        if val:
            row[col] = val
    return row


def _collect_mappings() -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Interactively collect one or more mapping rows.
    The user can also add extra columns that will be present for *all*
    rows.
    Returns the list of rows and the full list of column names (including the
    extra ones).
    """
    print("\n=== MAPPINGS INPUT ===")
    print(
        "You will be asked to enter the required SSSOM columns:\n"
        "  * subject_id\n"
        "  * predicate_id\n"
        "  * object_id\n"
        "\nYou may also define extra columns that will be present for every "
        "row (e.g. confidence, mapping_tool, etc.).\n"
    )

    # First, ask which *extra* columns the user wants.
    extra_columns: List[str] = []
    while True:
        col = input("Add an extra column name (blank when done): ").strip()
        if not col:
            break
        if col in {"subject_id", "predicate_id", "object_id"}:
            print("  That name is reserved – it already exists.")
            continue
        extra_columns.append(col)

    # Collect rows
    rows: List[Dict[str, str]] = []
    while True:
        rows.append(_collect_one_mapping(extra_columns))
        another = input("\nAdd another mapping row? (y/N): ").strip().lower()
        if another != "y":
            break

    # Build the final field order: required columns first, then extras
    fieldnames = ["subject_id", "predicate_id", "object_id"] + extra_columns
    return rows, fieldnames


def write_sssom_file(
    metadata: Dict[str, str],
    rows: List[Dict[str, str]],
    fieldnames: List[str],
    output_path: Path,
) -> None:
    """
    Write the final SSSOM file (header comments + tab‑separated rows).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = output_path.with_suffix(".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        # Header comment lines
        for key in sorted(metadata):
            fh.write(f"# {key}: {metadata[key]}\n")
        # Body
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    tmp_path.replace(output_path)


def load(source: str = "manual.sssom.tsv", **kwargs) -> Dict[str, Any]:
    """Load manual mappings from existing file or prompt."""
    p = Path(source)
    if p.is_file():
        from src.load_from_sssom import load as load_sssom
        return load_sssom(str(p))
    return {
        "curie_map": {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "semapv": "https://w3id.org/semapv/vocab/",
        },
        "mappings": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Interactively create a small SSSOM file.  The user manually "
            "enters mapping rows and optional metadata, then the script "
            "writes a valid SSSOM TSV file."
        )
    )
    parser.add_argument(
        "-o",
        "--output",
        default="manual.sssom.tsv",
        help="File name (or path) for the generated SSSOM file. "
             "Defaults to ./manual.sssom.tsv",
    )
    args = parser.parse_args()

    # ----------------------------------------------------------------------
    # 1️⃣  Collect metadata
    # ----------------------------------------------------------------------
    metadata = _collect_metadata()

    # ----------------------------------------------------------------------
    # 2️⃣  Collect mappings (rows + column order)
    # ----------------------------------------------------------------------
    rows, fieldnames = _collect_mappings()

    # ----------------------------------------------------------------------
    # 3️⃣  Write the file
    # ----------------------------------------------------------------------
    out_path = Path(args.output).expanduser().resolve()
    print(f"\nWriting SSSOM file to {out_path}")
    write_sssom_file(metadata, rows, fieldnames, out_path)
    print("\n✅ Finished!  Your SSSOM file is ready.\n")


if __name__ == "__main__":
    main()