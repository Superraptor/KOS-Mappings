#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_sssom_metadata.py
--------------------------
Creates an SSSOM document (JSON) from any mapping source by delegating to
the appropriate loader module and enriching with repository and platform metadata.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import pathlib
import re
import sys
import urllib.parse
import uuid
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import requests

if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root and src directory are on sys.path
_SRC_DIR = pathlib.Path(__file__).resolve().parent
_ROOT_DIR = _SRC_DIR.parent
for d in [str(_SRC_DIR), str(_ROOT_DIR)]:
    if d not in sys.path:
        sys.path.insert(0, d)

LOGGER = logging.getLogger(__name__)

# ------------------------------------------------------------ #
# Helper utilities
# ------------------------------------------------------------ #
def _is_url(candidate: str) -> bool:
    return candidate.startswith("http://") or candidate.startswith("https://")


# ------------------------------------------------------------ #
# Platform‑specific metadata extraction (GitHub / SourceForge)
# ------------------------------------------------------------ #
GITHUB_RE = re.compile(
    r"https?://(?:raw\.githubusercontent\.com|(?:www\.)?github\.com)/(?P<owner>[^/]+)/(?P<repo>[^/]+)(?:/(?:raw|blob|tree))?/(?P<ref>[^/]+)/(?P<path>.+)"
)


def _extract_github_metadata(file_url: str, token: Optional[str] = None) -> Mapping[str, Any]:
    meta: Dict[str, Any] = {}
    try:
        from src.retrieve_github_metadata import get_repo_file_metadata
        gh_data = get_repo_file_metadata(file_url)
        if isinstance(gh_data, dict):
            if "file_metadata" in gh_data and isinstance(gh_data["file_metadata"], dict):
                sha = gh_data["file_metadata"].get("sha")
                if sha:
                    meta["github_commit_sha"] = sha
            if "file_contributors" in gh_data and isinstance(gh_data["file_contributors"], list):
                if gh_data["file_contributors"]:
                    first_contrib = gh_data["file_contributors"][0]
                    c_date = first_contrib.get("date")
                    if c_date:
                        meta["publication_date"] = str(c_date)[:10]
            if "repo_license" in gh_data and isinstance(gh_data["repo_license"], dict):
                lic_spdx = gh_data["repo_license"].get("license", {}).get("spdx_id")
                if lic_spdx and lic_spdx != "NOASSERTION":
                    meta["license"] = lic_spdx
    except Exception as exc:
        LOGGER.debug("retrieve_github_metadata failed: %s", exc)

    m = GITHUB_RE.match(file_url)
    if m:
        owner, repo = m.group("owner"), m.group("repo")
        meta["github_owner"] = owner
        meta["github_repo"] = repo
    meta["source_url"] = file_url
    return meta


def _extract_sourceforge_metadata(file_url: str) -> Mapping[str, Any]:
    meta: Dict[str, Any] = {"mapping_provider": "SourceForge", "source_url": file_url}
    try:
        from src.retrieve_sourceforge_metadata import get_sourceforge_metadata
        sf_data = get_sourceforge_metadata(file_url)
        if isinstance(sf_data, dict):
            history = sf_data.get("file_history")
            if isinstance(history, list) and history:
                latest = history[0]
                if "revision" in latest:
                    meta["mapping_set_version"] = f"r{latest['revision']}"
                if "date" in latest:
                    meta["publication_date"] = str(latest["date"])[:10]
    except Exception as exc:
        LOGGER.debug("retrieve_sourceforge_metadata failed: %s", exc)
    return meta


def _extract_platform_metadata(source: str, github_token: Optional[str] = None) -> Mapping[str, Any]:
    if not _is_url(source):
        return {}

    source_lower = source.lower()
    if "github.com" in source_lower or "raw.githubusercontent.com" in source_lower:
        return _extract_github_metadata(source, github_token)
    if "sourceforge.net" in source_lower:
        return _extract_sourceforge_metadata(source)

    return {}


# ------------------------------------------------------------ #
# SSSOM document builder
# ------------------------------------------------------------ #
def _build_sssom_document(
    mappings: List[Dict[str, Any]],
    *,
    source_file: Optional[str] = None,
    source_url: Optional[str] = None,
    curie_map: Optional[Mapping[str, str]] = None,
    license: Optional[str] = None,
    publication: Optional[str] = None,
    version: Optional[str] = None,
    subject_source: Optional[str] = None,
    subject_source_version: Optional[str] = None,
    object_source: Optional[str] = None,
    object_source_version: Optional[str] = None,
    mapping_tool: Optional[str] = None,
    mapping_tool_version: Optional[str] = None,
    extra_meta: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    # Determine prefix pair for canonical title and mapping_set_id
    p1, p2 = "mapping", "set"
    if mappings:
        first = mappings[0]
        s_id = str(first.get("subject_id", ""))
        o_id = str(first.get("object_id", ""))
        if ":" in s_id and ":" in o_id:
            p1 = s_id.split(":")[0]
            p2 = o_id.split(":")[0]

    mapping_set_id = f"https://w3id.org/commons/mappings/{p1}_{p2}"
    mapping_set_title = f"{p1.upper()} to {p2.upper()} Mappings"
    mapping_date = datetime.now().strftime("%Y-%m-%d")

    doc: Dict[str, Any] = {
        "mapping_set_id": mapping_set_id,
        "mapping_set_title": mapping_set_title,
        "mapping_date": mapping_date,
        "license": license or "CC0-1.0",
        "curie_map": dict(curie_map or {}),
        "mappings": mappings,
    }

    if source_file:
        doc["source_file"] = source_file
    if source_url:
        doc["mapping_provider"] = source_url
        doc["source_url"] = source_url
    if publication:
        doc["publication_date"] = publication
    if version:
        doc["mapping_set_version"] = version
    if subject_source:
        doc["subject_source"] = subject_source
    if subject_source_version:
        doc["subject_source_version"] = subject_source_version
    if object_source:
        doc["object_source"] = object_source
    if object_source_version:
        doc["object_source_version"] = object_source_version
    if mapping_tool:
        doc["mapping_tool"] = mapping_tool
    if mapping_tool_version:
        doc["mapping_tool_version"] = mapping_tool_version

    if extra_meta:
        for k, v in extra_meta.items():
            if k not in doc and isinstance(v, (str, int, float, bool, list, dict)):
                doc[k] = v

    return doc


# ------------------------------------------------------------ #
# Loader dispatch logic
# ------------------------------------------------------------ #
LOADER_MAP: Dict[str, str] = {
    "document": "load_from_document",
    "graph": "load_from_graph",
    "manual": "load_from_manual_input",
    "spreadsheet": "load_from_spreadsheet",
    "sssom": "load_from_sssom",
    "webpage": "load_from_webpage",
}


def _import_loader(module_name: str):
    """Import a loader module on-demand and return its load callable."""
    try:
        mod = __import__(module_name, fromlist=["load"])
        return getattr(mod, "load")
    except Exception:
        try:
            mod = __import__(f"src.{module_name}", fromlist=["load"])
            return getattr(mod, "load")
        except Exception as exc:
            LOGGER.error("Failed to import loader module '%s': %s", module_name, exc)
            raise


def _choose_loader_by_extension(source: str) -> str:
    """Decide which loader to use based on URL/file path patterns."""
    source_lower = source.lower()
    parsed = urllib.parse.urlparse(source_lower)
    clean_path = parsed.path.split("?")[0]

    if "doi.org" in source_lower:
        return "document"

    if clean_path.endswith((".ttl", ".rdf", ".owl", ".jsonld", ".nt", ".nq", ".n3")) or "?format=raw" in source_lower:
        return "graph"

    if clean_path.endswith((".sssom.tsv", ".sssom")):
        return "sssom"

    if clean_path.endswith((".xlsx", ".xls", ".ods", ".csv")):
        return "spreadsheet"

    if clean_path.endswith(".zip"):
        return "document"

    if clean_path.endswith(".txt"):
        return "document"

    if _is_url(source):
        return "webpage"

    return "document"


def _dispatch_load(source: str, args: argparse.Namespace) -> Dict[str, Any]:
    if getattr(args, "loader", None):
        loader_key = args.loader.lower()
    else:
        loader_key = _choose_loader_by_extension(source)

    module_name = LOADER_MAP[loader_key]
    LOGGER.info("Dispatching to loader '%s' (module %s)", loader_key, module_name)
    load_func = _import_loader(module_name)

    extra_kwargs: Dict[str, Any] = {}
    if loader_key == "spreadsheet":
        extra_kwargs["sheet_name"] = getattr(args, "sheet_name", 0)
        extra_kwargs["min_non_null"] = getattr(args, "min_non_null", 2)

    data = load_func(source, **extra_kwargs)
    if "mappings" not in data:
        raise ValueError(f"Loader '{loader_key}' did not return a 'mappings' key.")
    return data


def generate_metadata(
    source: str,
    *,
    loader: Optional[str] = None,
    sheet_name: Union[str, int] = 0,
    min_non_null: int = 2,
    curie_map: Optional[Dict[str, str]] = None,
    license: Optional[str] = None,
    publication: Optional[str] = None,
    version: Optional[str] = None,
    github_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Programmatic entry point to generate SSSOM metadata and mapping document."""
    args = argparse.Namespace(
        file=source,
        loader=loader,
        sheet_name=sheet_name,
        min_non_null=min_non_null,
        curie_map=curie_map,
        license=license,
        publication=publication,
        version=version,
        github_token=github_token,
    )
    data = _dispatch_load(source, args)
    platform_meta = _extract_platform_metadata(source, github_token=github_token)

    merged_curie_map = dict(curie_map or {})
    if "curie_map" in data and isinstance(data["curie_map"], dict):
        merged_curie_map.update(data["curie_map"])

    sssom_doc = _build_sssom_document(
        mappings=data["mappings"],
        source_file=pathlib.Path(source).name if not _is_url(source) else None,
        source_url=source if _is_url(source) else None,
        curie_map=merged_curie_map,
        license=license or data.get("license"),
        publication=publication or data.get("publication_date"),
        version=version or data.get("mapping_set_version"),
        subject_source=data.get("subject_source"),
        subject_source_version=data.get("subject_source_version"),
        object_source=data.get("object_source"),
        object_source_version=data.get("object_source_version"),
        mapping_tool=data.get("mapping_tool"),
        mapping_tool_version=data.get("mapping_tool_version"),
        extra_meta=platform_meta,
    )
    return sssom_doc


def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate SSSOM document from mapping source.")
    parser.add_argument("file", nargs="?", help="Path or URL to mapping source.")
    parser.add_argument("--sheet-name", default=0, help="Excel sheet index/name.")
    parser.add_argument("--min-non-null", type=int, default=2, help="Min non-null cells.")
    parser.add_argument("--curie-map", type=json.loads, help="JSON string of CURIE prefix map.")
    parser.add_argument("--license", help="License identifier.")
    parser.add_argument("--publication", help="Publication info.")
    parser.add_argument("--version", help="Version string.")
    parser.add_argument("--output", "-o", type=pathlib.Path, help="Write SSSOM JSON output to file.")
    parser.add_argument("--github-token", help="GitHub API personal access token.")
    parser.add_argument("--loader", choices=sorted(LOADER_MAP.keys()), help="Force specific loader.")
    return parser.parse_args()


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parse_cli()
    if not args.file:
        LOGGER.error("No input source supplied. Provide a path/URL.")
        sys.exit(1)

    try:
        sssom_doc = generate_metadata(
            str(args.file),
            loader=args.loader,
            sheet_name=args.sheet_name,
            min_non_null=args.min_non_null,
            curie_map=args.curie_map,
            license=args.license,
            publication=args.publication,
            version=args.version,
            github_token=args.github_token,
        )
    except Exception as exc:
        LOGGER.exception("Loading failed: %s", exc)
        sys.exit(1)

    json_str = json.dumps(sssom_doc, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_str, encoding="utf-8")
        LOGGER.info("SSSOM document written to %s", args.output)
    else:
        print(json_str)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()