#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
src/sync_mapping_commons_registry.py
------------------------------------
Discovers, downloads, and ingests SSSOM mapping sets from the official
Mapping Commons Registry (https://mapping-commons.github.io/).

Features:
- Fetches live catalog from https://mapping-commons.github.io/data/mapping-specifications.json
- Filters by registry community (Mouse Human, Monarch, EBI, C-Path, etc.)
- Ingests into canonical ./commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv
- Enriches every row with full metadata and filters per-file CURIE maps
- Automatically deduplicates and merges with existing repository mappings

Usage:
    python src/sync_mapping_commons_registry.py --list
    python src/sync_mapping_commons_registry.py --registry "Mouse Human Mapping Initiative"
    python src/sync_mapping_commons_registry.py --limit 5
    python src/sync_mapping_commons_registry.py --all
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_SRC_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SRC_DIR.parent
for d in [str(_SRC_DIR), str(_ROOT_DIR)]:
    if d not in sys.path:
        sys.path.insert(0, d)

from src.write_sssom_file import write_sssom_file

LOGGER = logging.getLogger("sync_mapping_commons_registry")

REGISTRY_SPECS_URL = "https://mapping-commons.github.io/data/mapping-specifications.json"


def fetch_registry_specifications(
    url: str = REGISTRY_SPECS_URL,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """
    Retrieves the complete list of mapping specifications published at
    https://mapping-commons.github.io/.
    """
    LOGGER.info("Fetching mapping specifications from %s", url)
    headers = {"User-Agent": "KOS-Mappings-Sync/1.0 (https://github.com/Superraptor/KOS-Mappings)"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"Expected list of mapping specifications, got {type(data)}")
    return data


def group_specs_by_registry(specs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Groups mapping specifications by registry name or ID.
    """
    by_reg: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for s in specs:
        regs = s.get("registries") or []
        if not regs:
            by_reg["Uncategorized"].append(s)
            continue
        for r in regs:
            name = r.get("name") or r.get("id") or "Unknown"
            by_reg[name].append(s)
    return by_reg


def list_registry_catalog(specs: List[Dict[str, Any]]) -> None:
    """
    Prints a summary of all registries and mapping specifications.
    """
    by_reg = group_specs_by_registry(specs)
    total_sssom = sum(1 for s in specs if s.get("type") == "sssom" and s.get("content_url"))

    print("\n" + "=" * 70)
    print(f" Mapping Commons Registry Catalog ({len(specs)} specs, {total_sssom} SSSOM files)")
    print("=" * 70)

    for reg_name, items in sorted(by_reg.items(), key=lambda x: -len(x[1])):
        sssom_count = sum(1 for s in items if s.get("type") == "sssom" and s.get("content_url"))
        print(f"\n📂 Registry: {reg_name} ({len(items)} items, {sssom_count} SSSOM)")
        for i, s in enumerate(items[:5], 1):
            s_id = s.get("id", "")
            c_url = s.get("content_url", "")
            s_type = s.get("type", "")
            print(f"   {i}. [{s_type}] {s_id}")
            if c_url and c_url != s_id:
                print(f"      URL: {c_url}")
        if len(items) > 5:
            print(f"      ... and {len(items) - 5} more")

    print("\n" + "=" * 70 + "\n")


def sync_specifications(
    specs: List[Dict[str, Any]],
    *,
    registry_filter: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    auto_accept: bool = True,
) -> Tuple[int, int, List[Path]]:
    """
    Downloads and ingests matching specifications into canonical ./commons files.
    Returns (success_count, fail_count, list_of_written_paths).
    """
    candidates = []
    reg_lower = registry_filter.lower() if registry_filter else None

    for s in specs:
        if s.get("type") != "sssom":
            continue
        c_url = s.get("content_url")
        if not c_url:
            continue

        if reg_lower:
            regs = s.get("registries") or []
            match = any(
                reg_lower in (r.get("name") or "").lower() or reg_lower in (r.get("id") or "").lower()
                for r in regs
            )
            if not match:
                continue

        candidates.append(s)

    if limit and limit > 0:
        candidates = candidates[:limit]

    print(f"\n🚀 Selected {len(candidates)} SSSOM mapping specification(s) to synchronize.")
    if dry_run:
        print("🔍 DRY RUN: No files will be modified.")
        for i, c in enumerate(candidates, 1):
            print(f"  {i}. {c.get('id')} -> {c.get('content_url')}")
        return len(candidates), 0, []

    success_count = 0
    fail_count = 0
    all_written_paths: List[Path] = []

    for idx, c in enumerate(candidates, 1):
        c_url = c["content_url"]
        m_id = c.get("id", c_url)
        print(f"\n[{idx:03d}/{len(candidates):03d}] Ingesting: {m_id}")
        print(f"  URL: {c_url}")

        try:
            written = write_sssom_file(
                c_url,
                yes=auto_accept,
                no_edit=True,
            )
            success_count += 1
            all_written_paths.extend(written)
            print(f"  ✔ Successfully processed ({len(written)} canonical file(s) updated)")
        except Exception as exc:
            fail_count += 1
            LOGGER.error("Failed to ingest %s: %s", c_url, exc)
            print(f"  ❌ Error: {exc}")

    print("\n" + "=" * 70)
    print(f" Sync Complete: {success_count} succeeded, {fail_count} failed.")
    print(f" Total Canonical Files Written/Updated: {len(set(all_written_paths))}")
    print("=" * 70 + "\n")

    return success_count, fail_count, all_written_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize mappings from the Mapping Commons Registry (https://mapping-commons.github.io/)."
    )
    parser.add_argument("--list", action="store_true", help="List all registries and specifications without ingesting.")
    parser.add_argument("--registry", "-r", help="Filter by registry name or substring (e.g. 'Mouse Human').")
    parser.add_argument("--limit", "-n", type=int, default=None, help="Limit number of specifications to ingest.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate synchronization without writing files.")
    parser.add_argument("--all", action="store_true", help="Ingest all available SSSOM specifications.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging.")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    try:
        specs = fetch_registry_specifications()
    except Exception as exc:
        LOGGER.exception("Could not retrieve Mapping Commons specifications: %s", exc)
        sys.exit(1)

    if args.list:
        list_registry_catalog(specs)
        return

    if not args.registry and not args.limit and not args.all and not args.dry_run:
        print("No filter or action specified. Listing registry catalog (use --registry, --limit, or --all to sync):")
        list_registry_catalog(specs)
        return

    sync_specifications(
        specs,
        registry_filter=args.registry,
        limit=args.limit,
        dry_run=args.dry_run,
        auto_accept=True,
    )


if __name__ == "__main__":
    main()
