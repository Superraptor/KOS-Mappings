#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
build_web_index.py
------------------
Aggregates all SSSOM mapping files in ./commons/ into a lightweight JSON graph index
for the ./www web application and GitHub Pages deployment.
Outputs:
  - www/data/mappings_graph.json
  - www/data/endpoints.json (via generate_endpoints_reference)
"""

import csv
import gzip
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

_SRC_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SRC_DIR.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

_COMMONS_DIR = _ROOT_DIR / "commons"
_WWW_DATA_DIR = _ROOT_DIR / "www" / "data"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger(__name__)


def _open_file(path: Path):
    if path.name.lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def build_index() -> Dict[str, Any]:
    from src.generate_endpoints_reference import build_endpoint_registry
    LOGGER.info("Generating endpoint reference dictionary...")
    endpoint_records = build_endpoint_registry()
    endpoint_map = {rec["prefix"]: rec for rec in endpoint_records}

    LOGGER.info("Scanning commons directory for SSSOM mapping files...")
    edges: List[Dict[str, Any]] = []
    node_mapping_counts = defaultdict(int)
    node_degrees = defaultdict(set)
    total_mappings = 0

    all_sample_mappings = []

    tsv_files = sorted(list(_COMMONS_DIR.glob("*/*/*.sssom.tsv*")))
    LOGGER.info("Found %d SSSOM files in commons.", len(tsv_files))

    for tsv_path in tsv_files:
        p_name = tsv_path.name
        # Skip temporary files
        if ".tmp" in p_name:
            continue
        # Extract subject and object prefix from folder/filename
        p1 = tsv_path.parent.parent.name
        p2 = tsv_path.parent.name

        predicate_counts = defaultdict(int)
        sample_rows = []
        file_row_count = 0
        header_meta = {}

        try:
            with _open_file(tsv_path) as f:
                header_lines = []
                data_lines = []
                for line in f:
                    s_line = line.strip()
                    if s_line.startswith("#"):
                        if ":" in s_line:
                            clean = s_line.lstrip("#").strip()
                            k, v = clean.split(":", 1)
                            header_meta[k.strip()] = v.strip().strip("'\"")
                    elif s_line:
                        data_lines.append(line)

                if data_lines:
                    reader = csv.DictReader(data_lines, delimiter="\t")
                    for row in reader:
                        file_row_count += 1
                        pred = row.get("predicate_id", "skos:relatedMatch")
                        predicate_counts[pred] += 1

                        if len(sample_rows) < 6:
                            sample_rows.append({
                                "subject_id": row.get("subject_id", ""),
                                "subject_label": row.get("subject_label", ""),
                                "predicate_id": pred,
                                "object_id": row.get("object_id", ""),
                                "object_label": row.get("object_label", ""),
                                "mapping_justification": row.get("mapping_justification", ""),
                                "mapping_date": row.get("mapping_date", ""),
                            })

                        if len(all_sample_mappings) < 1500 and (file_row_count % max(1, file_row_count // 5) == 0):
                            all_sample_mappings.append({
                                "source": p1,
                                "target": p2,
                                "subject_id": row.get("subject_id", ""),
                                "subject_label": row.get("subject_label", ""),
                                "predicate_id": pred,
                                "object_id": row.get("object_id", ""),
                                "object_label": row.get("object_label", ""),
                                "mapping_justification": row.get("mapping_justification", ""),
                            })

        except Exception as exc:
            LOGGER.warning("Could not read %s: %s", tsv_path, exc)
            continue

        if file_row_count == 0:
            continue

        rel_path = str(tsv_path.relative_to(_ROOT_DIR)).replace("\\", "/")
        edge_info = {
            "source": p1,
            "target": p2,
            "count": file_row_count,
            "predicates": dict(predicate_counts),
            "file": rel_path,
            "mapping_set_id": header_meta.get("mapping_set_id", f"https://w3id.org/commons/mappings/{p1}_{p2}"),
            "mapping_set_title": header_meta.get("mapping_set_title", f"{p1.upper()} to {p2.upper()} Mappings"),
            "license": header_meta.get("license", "CC0-1.0"),
            "samples": sample_rows,
        }
        edges.append(edge_info)

        total_mappings += file_row_count
        node_mapping_counts[p1] += file_row_count
        node_mapping_counts[p2] += file_row_count
        node_degrees[p1].add(p2)
        node_degrees[p2].add(p1)

    # Build node objects
    all_prefixes = sorted(set(list(node_mapping_counts.keys())))
    nodes = []
    for pfx in all_prefixes:
        meta = endpoint_map.get(pfx, {})
        nodes.append({
            "id": pfx,
            "name": meta.get("name", pfx.upper()),
            "category": meta.get("category", "General"),
            "authority": meta.get("authority", "Mapping Commons"),
            "uri_prefix": meta.get("uri_prefix", f"https://identifiers.org/{pfx}:"),
            "description": meta.get("description", f"Ontology endpoint {pfx}."),
            "mapping_count": node_mapping_counts[pfx],
            "degree": len(node_degrees[pfx]),
        })

    # Build adjacency list for fast client-side shortest path graph search
    adjacency = defaultdict(list)
    for edge in edges:
        adjacency[edge["source"]].append({
            "neighbor": edge["target"],
            "count": edge["count"],
            "predicates": edge["predicates"],
            "file": edge["file"],
            "samples": edge["samples"],
            "direction": "forward",
        })
        # Add reverse edge for bidirected navigation
        adjacency[edge["target"]].append({
            "neighbor": edge["source"],
            "count": edge["count"],
            "predicates": edge["predicates"],
            "file": edge["file"],
            "samples": edge["samples"],
            "direction": "reverse",
        })

    graph_data = {
        "stats": {
            "total_vocabularies": len(nodes),
            "total_mapping_sets": len(edges),
            "total_mappings": total_mappings,
        },
        "nodes": nodes,
        "edges": edges,
        "adjacency": dict(adjacency),
        "search_samples": all_sample_mappings,
    }

    _WWW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_json = _WWW_DATA_DIR / "mappings_graph.json"
    out_json.write_text(json.dumps(graph_data, indent=2), encoding="utf-8")
    LOGGER.info(
        "Successfully built web graph index: %d nodes, %d edges, %d total mappings -> %s",
        len(nodes), len(edges), total_mappings, out_json
    )
    return graph_data


if __name__ == "__main__":
    build_index()
