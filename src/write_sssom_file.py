#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
src/write_sssom_file.py
-----------------------
Orchestrates SSSOM metadata generation, review, and writing/merging into
the canonical Mapping Commons directory structure:

    commons/<prefix-1>/<prefix-2>/<prefix-1>_<prefix-2>.sssom.tsv

Produces SSSOM-compliant TSV files with embedded YAML header comments
conforming to Mapping Commons Registry specifications.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root and src directory are on sys.path
_SRC_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SRC_DIR.parent
for d in [str(_SRC_DIR), str(_ROOT_DIR)]:
    if d not in sys.path:
        sys.path.insert(0, d)

LOGGER = logging.getLogger(__name__)

MANDATORY_COLUMNS = ["subject_id", "predicate_id", "object_id", "mapping_justification"]

CANONICAL_COLUMN_ORDER = [
    "subject_id",
    "predicate_id",
    "object_id",
    "mapping_justification",
    "subject_label",
    "object_label",
    "subject_source",
    "subject_source_version",
    "object_source",
    "object_source_version",
    "mapping_tool",
    "mapping_tool_version",
    "mapping_date",
    "mapping_provider",
    "confidence",
    "author_id",
    "author_label",
    "creator_id",
    "creator_label",
    "license",
    "comment",
]

STANDARD_PREFIX_MAP: Dict[str, str] = {
    # Core W3C & semantics
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "semapv": "https://w3id.org/semapv/vocab/",
    "sssom": "https://w3id.org/sssom/",
    "schema": "http://schema.org/",
    "dcterms": "http://purl.org/dc/terms/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "prov": "http://www.w3.org/ns/prov#",
    "dcat": "http://www.w3.org/ns/dcat#",
    "dcatap": "http://data.europa.eu/r5r/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "vcard": "http://www.w3.org/2006/vcard/ns#",
    "adms": "http://www.w3.org/ns/adms#",
    # Identifiers & people
    "orcid": "https://orcid.org/",
    "wikidata": "http://www.wikidata.org/entity/",
    "isbn": "urn:isbn:",
    "issn": "urn:issn:",
    "doi": "https://doi.org/",
    # OBO & Biomedicine
    "doid": "http://purl.obolibrary.org/obo/DOID_",
    "mesh": "http://id.nlm.nih.gov/mesh/",
    "mondo": "http://purl.obolibrary.org/obo/MONDO_",
    "hp": "http://purl.obolibrary.org/obo/HP_",
    "chebi": "http://purl.obolibrary.org/obo/CHEBI_",
    "cl": "http://purl.obolibrary.org/obo/CL_",
    "go": "http://purl.obolibrary.org/obo/GO_",
    "uberon": "http://purl.obolibrary.org/obo/UBERON_",
    "ncbitaxon": "http://purl.obolibrary.org/obo/NCBITaxon_",
    "pr": "http://purl.obolibrary.org/obo/PR_",
    "so": "http://purl.obolibrary.org/obo/SO_",
    "symp": "http://purl.obolibrary.org/obo/SYMP_",
    "bfo": "http://purl.obolibrary.org/obo/BFO_",
    "ro": "http://purl.obolibrary.org/obo/RO_",
    "obo": "http://purl.obolibrary.org/obo/",
    # Health classifications & Athena vocabularies
    "icd10": "https://icd.who.int/browse10/2019/en#/",
    "icd11": "http://id.who.int/icd/entity/",
    "icd10cm": "https://identifiers.org/icd10cm:",
    "icd9cm": "https://identifiers.org/icd9cm:",
    "snomedct": "http://snomed.info/id/",
    "loinc": "https://loinc.org/",
    "ucum": "http://unitsofmeasure.org/",
    "omopext": "https://athena.ohdsi.org/search-terms/terms/",
    "omop": "https://athena.ohdsi.org/search-terms/terms/",
    "osm": "https://www.openstreetmap.org/",
    "uscensus": "https://www.census.gov/",
    "rxnorm": "https://identifiers.org/rxnorm:",
    "rxnormext": "https://athena.ohdsi.org/search-terms/terms/",
    "cpt": "https://identifiers.org/cpt:",
    "hcpcs": "https://identifiers.org/hcpcs:",
    "atc": "https://identifiers.org/atc:",
    "ndc": "https://identifiers.org/ndc:",
    "meddra": "https://identifiers.org/meddra:",
    "ncit": "http://purl.obolibrary.org/obo/NCIT_",
    "umls": "https://identifiers.org/umls:",
    # Library & Knowledge Schemes
    "lcsh": "http://id.loc.gov/authorities/subjects/",
    "gnd": "https://d-nb.info/gnd/",
    "viaf": "http://viaf.org/viaf/",
    "fast": "http://id.worldcat.org/fast/",
    "ebsco": "https://www.ebsco.com/terms/",
    "rda": "http://rdaregistry.info/Elements/",
    # Upper & Domain Ontologies
    "dbo": "http://dbpedia.org/ontology/",
    "dbpedia": "http://dbpedia.org/resource/",
    "dbr": "http://dbpedia.org/resource/",
    "yago": "http://yago-knowledge.org/resource/",
    "wikipedia": "http://en.wikipedia.org/wiki/",
    "wn": "http://www.ontologyportal.org/WordNet.owl#",
    "wordnet": "http://www.ontologyportal.org/WordNet.owl#",
    "sumo": "http://www.ontologyportal.org/SUMO.owl#",
    "bibo": "http://purl.org/ontology/bibo/",
    "fabio": "http://purl.org/spar/fabio/",
    "cito": "http://purl.org/spar/cito/",
    "gfo": "http://www.onto-med.de/ontologies/gfo.owl#",
    "dolce": "http://www.loa-cnr.it/ontologies/DOLCE-Lite.owl#",
    "temporalrelations": "http://www.loa-cnr.it/ontologies/TemporalRelations.owl#",
    "spatialrelations": "http://www.loa-cnr.it/ontologies/SpatialRelations.owl#",
    "functionalparticipation": "http://www.loa-cnr.it/ontologies/FunctionalParticipation.owl#",
    "opencyc": "http://sw.opencyc.org/concept/",
    "biomappings": "https://biopragmatics.github.io/biomappings/",
}

KNOWN_SOURCE_VERSIONS: Dict[str, str] = {
    "icd10": "2019",
    "icd11": "2024-01",
    "icd10cm": "2018",
    "icd9cm": "2017",
    "snomedct": "2026-02-01",
    "loinc": "2.82",
    "ucum": "1.8.2",
    "dcat": "2.1.1",
    "dcatap": "2.1.1",
    "schema": "26.0",
    "lcsh": "2024",
    "mesh": "2024",
    "ebsco": "2024",
    "issn": "2024",
    "isbn": "2024",
    "rda": "2024",
    "bfo": "1.1",
    "gfo": "1.0",
    "dolce": "397",
    "ro": "1.0",
    "temporalrelations": "1.0",
    "spatialrelations": "1.0",
    "functionalparticipation": "1.0",
}

KNOWN_ORIGINATION_DATES: Dict[str, str] = {
    "athena": "2026-08-29",
    "ohdsi": "2026-08-29",
    "icd10cm_icd9cm": "2017-10-01",
    "icd9cm_icd10cm": "2017-10-01",
    "icd10pcs_icd9pcs": "2017-10-01",
    "icd9pcs_icd10pcs": "2017-10-01",
    "gem": "2017-10-01",
    "icd10_icd11": "2024-01-01",
    "icd11_icd10": "2024-01-01",
    "galter": "2018-03-27",
    "lcsh_mesh": "2018-03-27",
    "mesh_lcsh": "2018-03-27",
    "ebsco": "2024-01-01",
    "rda": "2022-03-09",
    "datacite-to-dcat-ap": "2021-06-25",
    "dcat-ap-to-schema-org": "2019-12-05",
    "dcat-prov": "2013-04-30",
    "prov-dc": "2013-04-30",
    "prov-bfo": "2025-01-19",
    "sio-ro": "2014-03-12",
    "bibo2spar": "2018-06-21",
    "bibo.ttl": "2011-12-01",
    "sumo-dbpedia": "2010-09-01",
    "sumo_owl": "2013-10-08",
    "romulus": "2012-11-21",
    "mondo": "2026-10-06",
    "schemaorg": "2024-04-04",
    "schema": "2024-04-04",
}

KNOWN_MAPPING_SET_VERSIONS: Dict[str, str] = {
    "schemaorg": "26.0",
    "schema": "26.0",
    "bibo2spar": "2018-06-21",
    "dcat-prov": "2013-04-30",
    "prov-dc": "2013-04-30",
    "romulus": "2012-11-21",
    "biomappings": "ed12b9f4",
    "mondo": "2026-10-06",
    "gem": "2018",
    "ebsco": "2024",
    "rda": "2022-03-09",
    "datacite-to-dcat-ap": "2021-06-25",
    "dcat-ap-to-schema-org": "2019-12-05",
}


def is_system_date(val: Optional[Any]) -> bool:
    """
    Returns True if the date was created or defaulted by this pipeline system
    (e.g., system run execution dates like 2026-11-* or current datetime.now())
    rather than derived from an authentic source file, repository commit, or changelog.
    """
    if val is None:
        return False
    v_str = str(val).strip().strip("'\"")
    if not v_str:
        return False
    if v_str.startswith("2026-11"):
        return True
    try:
        if v_str == datetime.now().strftime("%Y-%m-%d"):
            return True
    except Exception:
        pass
    return False

_URI_SCHEMES = {
    "http", "https", "ftp", "ftps", "file", "mailto", "data", "javascript", "tel", "urn"
}
_CURIE_PATTERN = re.compile(r"\b([a-zA-Z][a-zA-Z0-9_\-\.]*):([a-zA-Z0-9_\-\.\/#%]+)")

_CURIE_SLOTS = {
    "subject_id",
    "predicate_id",
    "object_id",
    "subject",
    "predicate",
    "object",
    "mapping_justification",
    "justification",
    "author_id",
    "creator_id",
    "reviewer_id",
    "mapping_tool_id",
    "subject_category",
    "object_category",
    "subject_type",
    "object_type",
    "predicate_modifier",
    "mapping_provider",
    "license",
    "similarity_measure",
    "subject_source",
    "object_source",
}

_EXCLUDED_TEXT_FIELDS = {
    "subject_label",
    "object_label",
    "comment",
    "mapping_tool",
    "mapping_tool_version",
    "subject_source_version",
    "object_source_version",
    "mapping_set_title",
    "mapping_set_description",
    "mapping_date",
    "confidence",
    "semantic_similarity_score",
    "match_type",
}


def _extract_used_prefixes(
    rows: Iterable[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
    p1: Optional[str] = None,
    p2: Optional[str] = None,
) -> Set[str]:
    """
    Scans mapping rows and header metadata to identify all CURIE prefixes
    actually referenced by the entities in a specific SSSOM file.
    Strictly checks CURIE entity slots and ignores free-text labels/comments.
    """
    used: Set[str] = set()

    if p1:
        clean_p1 = re.sub(r"[^a-zA-Z0-9_\-\.]", "", str(p1)).lower()
        if clean_p1 and clean_p1 not in _URI_SCHEMES:
            used.add(clean_p1)
    if p2:
        clean_p2 = re.sub(r"[^a-zA-Z0-9_\-\.]", "", str(p2)).lower()
        if clean_p2 and clean_p2 not in _URI_SCHEMES:
            used.add(clean_p2)

    for row in rows:
        for k, val in row.items():
            if not isinstance(val, str) or not val:
                continue
            k_lower = str(k).lower().strip()
            if k_lower in _EXCLUDED_TEXT_FIELDS:
                continue
            if not (
                k_lower in _CURIE_SLOTS
                or k_lower.endswith(("_id", "_curie", "_source", "_justification"))
            ):
                continue

            for token in val.split("|"):
                token = token.strip()
                if not token or token.startswith(("http://", "https://", "urn:", "ftp://", "file://")):
                    continue
                if ":" in token:
                    pfx, _, _ = token.partition(":")
                    pfx = pfx.strip().lower()
                    if pfx and pfx not in _URI_SCHEMES and re.match(r"^[a-zA-Z][a-zA-Z0-9_\-\.]*$", pfx):
                        used.add(pfx)
                elif k_lower in ("subject_source", "object_source"):
                    clean_p = re.sub(r"[^a-zA-Z0-9_\-\.]", "", token).lower()
                    if clean_p and clean_p not in _URI_SCHEMES and re.match(r"^[a-zA-Z][a-zA-Z0-9_\-\.]*$", clean_p):
                        used.add(clean_p)

    if metadata:
        for k, v in metadata.items():
            k_lower = str(k).lower().strip()
            if k in ("curie_map", "mappings", "review") or k_lower in _EXCLUDED_TEXT_FIELDS:
                continue
            if k in ("subject_source", "object_source") and isinstance(v, str):
                clean_p = re.sub(r"[^a-zA-Z0-9_\-\.]", "", v).lower()
                if clean_p and clean_p not in _URI_SCHEMES:
                    used.add(clean_p)
            elif isinstance(v, str) and ":" in v:
                for token in v.split("|"):
                    token = token.strip()
                    if not token or token.startswith(("http://", "https://", "urn:", "ftp://", "file://")):
                        continue
                    if ":" in token:
                        pfx, _, _ = token.partition(":")
                        pfx = pfx.strip().lower()
                        if pfx and pfx not in _URI_SCHEMES and re.match(r"^[a-zA-Z][a-zA-Z0-9_\-\.]*$", pfx):
                            used.add(pfx)

    return used


def _filter_curie_map(
    source_curie_map: Optional[Dict[str, str]],
    rows: Iterable[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
    p1: Optional[str] = None,
    p2: Optional[str] = None,
) -> Dict[str, str]:
    """
    Filters the CURIE map to strictly include ONLY the prefixes used by
    the entities and metadata in this specific SSSOM file.
    """
    used = _extract_used_prefixes(rows, metadata, p1, p2)
    source_cmap = dict(source_curie_map or {})
    lower_source_cmap = {k.lower(): (k, v) for k, v in source_cmap.items()}

    filtered: Dict[str, str] = {}
    for pfx in sorted(used):
        pfx_lower = pfx.lower()
        if pfx_lower in STANDARD_PREFIX_MAP:
            filtered[pfx] = STANDARD_PREFIX_MAP[pfx_lower]
        elif pfx_lower in lower_source_cmap:
            orig_k, ns = lower_source_cmap[pfx_lower]
            if ns and str(ns).startswith(("http://", "https://", "urn:")):
                filtered[pfx] = str(ns)
            else:
                filtered[pfx] = f"https://identifiers.org/{pfx}:"
        else:
            filtered[pfx] = f"https://identifiers.org/{pfx}:"

    return filtered


def _resolve_structure_metadata(
    p1: str,
    p2: str,
    group_rows: List[Dict[str, Any]],
    metadata: Dict[str, Any],
) -> Dict[str, str]:
    """
    Resolves subject/object sources, their versions, and mapping set version.
    """
    resolved: Dict[str, str] = {}

    # Subject & Object sources
    resolved["subject_source"] = str(metadata.get("subject_source") or p1).strip()
    resolved["object_source"] = str(metadata.get("object_source") or p2).strip()

    # Subject source version
    subj_row_versions = [
        str(r["subject_source_version"]).strip()
        for r in group_rows
        if str(r.get("subject_source_version", "")).strip()
    ]
    if subj_row_versions:
        resolved["subject_source_version"] = sorted(subj_row_versions)[-1]
    elif metadata.get("subject_source_version"):
        resolved["subject_source_version"] = str(metadata["subject_source_version"]).strip()
    elif p1 in KNOWN_SOURCE_VERSIONS:
        resolved["subject_source_version"] = KNOWN_SOURCE_VERSIONS[p1]

    # Object source version
    obj_row_versions = [
        str(r["object_source_version"]).strip()
        for r in group_rows
        if str(r.get("object_source_version", "")).strip()
    ]
    if obj_row_versions:
        resolved["object_source_version"] = sorted(obj_row_versions)[-1]
    elif metadata.get("object_source_version"):
        resolved["object_source_version"] = str(metadata["object_source_version"]).strip()
    elif p2 in KNOWN_SOURCE_VERSIONS:
        resolved["object_source_version"] = KNOWN_SOURCE_VERSIONS[p2]

    # Mapping set version: only retain if authentic / derived from source, commit, or known release
    pair = f"{p1}_{p2}".lower()
    pair_rev = f"{p2}_{p1}".lower()
    src_text = f"{metadata.get('mapping_provider', '')} {metadata.get('source_url', '')} {metadata.get('mapping_set_id', '')}".lower()
    known_ver = None
    if pair in KNOWN_MAPPING_SET_VERSIONS:
        known_ver = KNOWN_MAPPING_SET_VERSIONS[pair]
    elif pair_rev in KNOWN_MAPPING_SET_VERSIONS:
        known_ver = KNOWN_MAPPING_SET_VERSIONS[pair_rev]
    else:
        for k, v in KNOWN_MAPPING_SET_VERSIONS.items():
            if k in src_text:
                known_ver = v
                break

    meta_ver = metadata.get("mapping_set_version")
    if meta_ver and not is_system_date(meta_ver):
        resolved["mapping_set_version"] = str(meta_ver).strip()
    elif metadata.get("github_commit_sha"):
        resolved["mapping_set_version"] = str(metadata["github_commit_sha"])[:8].strip()
    elif known_ver:
        resolved["mapping_set_version"] = known_ver
    elif metadata.get("publication_date") and not is_system_date(metadata.get("publication_date")):
        resolved["mapping_set_version"] = str(metadata["publication_date"]).strip()
    elif metadata.get("mapping_date") and not is_system_date(metadata.get("mapping_date")):
        resolved["mapping_set_version"] = str(metadata["mapping_date"]).strip()

    # Mapping tool and version
    if metadata.get("mapping_tool"):
        resolved["mapping_tool"] = str(metadata["mapping_tool"]).strip()
    elif "biomappings" in str(metadata.get("mapping_provider", "")).lower():
        resolved["mapping_tool"] = "Biomappings"
    else:
        resolved["mapping_tool"] = "KOS-Mappings Pipeline"

    if metadata.get("mapping_tool_version"):
        resolved["mapping_tool_version"] = str(metadata["mapping_tool_version"]).strip()
    elif resolved["mapping_tool"] == "Biomappings":
        resolved["mapping_tool_version"] = "0.1.0"
    else:
        resolved["mapping_tool_version"] = "1.0.0"

    # License resolution: inherit from constituent rows or metadata
    lic = str(metadata.get("license") or "").strip()
    if not lic:
        row_lics = {str(r.get("license", "")).strip() for r in group_rows if str(r.get("license", "")).strip()}
        if len(row_lics) == 1 and list(row_lics)[0]:
            lic = list(row_lics)[0]
        else:
            lic = "https://w3id.org/sssom/license/unspecified"
    resolved["license"] = lic

    # Origination date resolution: only authentic dates derived from source file/repo/commit/changelog
    known_date = None
    if pair in KNOWN_ORIGINATION_DATES:
        known_date = KNOWN_ORIGINATION_DATES[pair]
    elif pair_rev in KNOWN_ORIGINATION_DATES:
        known_date = KNOWN_ORIGINATION_DATES[pair_rev]
    else:
        for k, v in KNOWN_ORIGINATION_DATES.items():
            if k in src_text:
                known_date = v
                break

    m_date = None
    if known_date:
        m_date = known_date
    else:
        raw_m_date = metadata.get("mapping_date")
        if raw_m_date and not is_system_date(raw_m_date):
            m_date = str(raw_m_date).strip()
        else:
            auth_row_dates = [
                str(r.get("mapping_date", "")).strip()
                for r in group_rows
                if str(r.get("mapping_date", "")).strip() and not is_system_date(r.get("mapping_date"))
            ]
            if auth_row_dates:
                m_date = sorted(auth_row_dates)[0]
            elif metadata.get("publication_date") and not is_system_date(metadata.get("publication_date")):
                m_date = str(metadata["publication_date"]).strip()

    if m_date and not is_system_date(m_date):
        resolved["mapping_date"] = m_date

    return resolved


def _enrich_row_metadata(
    rows: List[Dict[str, Any]],
    metadata: Dict[str, Any],
    p1: str,
    p2: str,
) -> List[Dict[str, Any]]:
    """
    Ensures each row contains all necessary metadata (subject/object sources,
    versions, mapping tool, date, provider, license) so that the row remains
    fully self-contained when new rows are added to the mapping file at later dates.
    """
    enriched: List[Dict[str, Any]] = []

    s_src = str(metadata.get("subject_source") or p1).strip()
    o_src = str(metadata.get("object_source") or p2).strip()
    s_ver = str(metadata.get("subject_source_version") or "").strip()
    o_ver = str(metadata.get("object_source_version") or "").strip()
    tool = str(metadata.get("mapping_tool") or "KOS-Mappings Pipeline").strip()
    tool_ver = str(metadata.get("mapping_tool_version") or "1.0.0").strip()
    
    # Resolve historical origination date for row enrichment
    pair = f"{p1}_{p2}".lower()
    pair_rev = f"{p2}_{p1}".lower()
    src_text = f"{metadata.get('mapping_provider', '')} {metadata.get('source_url', '')} {metadata.get('mapping_set_id', '')}".lower()
    known_date = None
    if pair in KNOWN_ORIGINATION_DATES:
        known_date = KNOWN_ORIGINATION_DATES[pair]
    elif pair_rev in KNOWN_ORIGINATION_DATES:
        known_date = KNOWN_ORIGINATION_DATES[pair_rev]
    else:
        for k, v in KNOWN_ORIGINATION_DATES.items():
            if k in src_text:
                known_date = v
                break

    provider = str(metadata.get("mapping_provider") or metadata.get("source_url") or "").strip()
    lic = str(metadata.get("license") or "").strip()
    if not lic:
        row_lics = {str(r.get("license", "")).strip() for r in rows if str(r.get("license", "")).strip()}
        if len(row_lics) == 1 and list(row_lics)[0]:
            lic = list(row_lics)[0]
        else:
            lic = "https://w3id.org/sssom/license/unspecified"

    for r in rows:
        row_dict = dict(r)

        # Mandatory columns
        just = str(row_dict.get("mapping_justification", "")).strip()
        if not just:
            row_dict["mapping_justification"] = "semapv:ManualMappingCuration"
        elif ";" in just or "|" in just:
            if "ManualMappingCuration" in just:
                row_dict["mapping_justification"] = "semapv:ManualMappingCuration"
            elif "LexicalMatching" in just:
                row_dict["mapping_justification"] = "semapv:LexicalMatching"
            else:
                row_dict["mapping_justification"] = re.split(r"[|;]", just)[0].strip()
        if not row_dict.get("predicate_id"):
            row_dict["predicate_id"] = "skos:exactMatch"

        # Row-level metadata enrichment (preserving existing row values)
        if not str(row_dict.get("subject_source", "")).strip():
            row_dict["subject_source"] = s_src
        if not str(row_dict.get("object_source", "")).strip():
            row_dict["object_source"] = o_src
        if not str(row_dict.get("subject_source_version", "")).strip() and s_ver:
            row_dict["subject_source_version"] = s_ver
        if not str(row_dict.get("object_source_version", "")).strip() and o_ver:
            row_dict["object_source_version"] = o_ver
        if not str(row_dict.get("mapping_tool", "")).strip():
            row_dict["mapping_tool"] = tool
        if not str(row_dict.get("mapping_tool_version", "")).strip():
            row_dict["mapping_tool_version"] = tool_ver
        
        row_date = str(row_dict.get("mapping_date", "")).strip()
        if row_date and not is_system_date(row_date):
            row_dict["mapping_date"] = row_date
        elif known_date:
            row_dict["mapping_date"] = known_date
        else:
            row_dict["mapping_date"] = ""
        if not str(row_dict.get("mapping_provider", "")).strip() and provider:
            row_dict["mapping_provider"] = provider
        if not str(row_dict.get("license", "")).strip():
            row_dict["license"] = lic

        enriched.append(row_dict)

    return enriched


# --------------------------------------------------------------
# 1️⃣  CALL THE REVIEW SCRIPT & GET THE METADATA (as JSON)
# --------------------------------------------------------------

def _run_review_script(
    location: str,
    *,
    yes: bool = False,
    no_edit: bool = False,
) -> Dict[str, Any]:
    """
    Executes review_metadata directly or via review_sssom_metadata.py subprocess.
    """
    try:
        from src.review_sssom_metadata import review_metadata
        return review_metadata(location, auto_accept=yes, no_edit=no_edit, emit_stdout=False)
    except Exception:
        try:
            from review_sssom_metadata import review_metadata
            return review_metadata(location, auto_accept=yes, no_edit=no_edit, emit_stdout=False)
        except Exception:
            pass

    review_script = Path(__file__).with_name("review_sssom_metadata.py")
    cmd = [sys.executable, str(review_script), location]
    if yes:
        cmd.append("-y")
    if no_edit:
        cmd.append("--no-edit")

    result = subprocess.run(
        cmd,
        cwd=str(_SRC_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"`review_sssom_metadata.py` failed (status {result.returncode}).\n"
            f"Stderr:\n{result.stderr}"
        )

    lines = result.stdout.splitlines()
    start_idx = next((i for i, l in enumerate(lines) if l.lstrip().startswith("{")), None)
    end_idx = next((i for i, l in enumerate(reversed(lines)) if l.rstrip().endswith("}")), None)
    if start_idx is None or end_idx is None:
        raise RuntimeError("Could not locate JSON output from review_sssom_metadata.py.")
    end_idx = len(lines) - 1 - end_idx
    json_text = "\n".join(lines[start_idx : end_idx + 1])
    return json.loads(json_text)


# --------------------------------------------------------------
# 2️⃣  HELPERS TO READ / WRITE SSSOM TSV FILES
# --------------------------------------------------------------

STANDARD_SSSOM_SLOTS = {
    "mapping_set_id",
    "mapping_set_version",
    "mapping_set_title",
    "mapping_set_description",
    "creator_id",
    "creator_label",
    "author_id",
    "author_label",
    "license",
    "subject_source",
    "subject_source_version",
    "object_source",
    "object_source_version",
    "mapping_provider",
    "mapping_tool",
    "mapping_tool_version",
    "mapping_date",
    "publication_date",
    "curie_map",
    "comment",
}


def _open_sssom_read(path: Path):
    """Open SSSOM file, detecting gzip automatically via extension or magic bytes."""
    try:
        with open(path, "rb") as bf:
            magic = bf.read(2)
        if magic == b"\x1f\x8b" or path.name.lower().endswith(".gz"):
            return gzip.open(path, "rt", newline="", encoding="utf-8", errors="replace")
    except Exception:
        pass
    return path.open(newline="", encoding="utf-8", errors="replace")


def _read_sssom_tsv(
    path: Path,
) -> Tuple[Dict[str, Any], List[Dict[str, str]], List[str]]:
    """
    Reads an existing SSSOM TSV file with YAML header comments (supports .sssom.tsv and .sssom.tsv.gz).
    """
    header_meta: Dict[str, Any] = {}
    curie_map: Dict[str, str] = {}
    rows: List[Dict[str, str]] = []
    fieldnames: List[str] = []

    in_curie_map = False
    data_lines = []

    with _open_sssom_read(path) as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\r\n")
            if line.startswith("#"):
                raw_comment = line[1:]
                comment = raw_comment.strip()
                if not comment:
                    continue
                if comment.startswith("curie_map:"):
                    in_curie_map = True
                    continue
                if in_curie_map:
                    is_indented = raw_comment.startswith("  ") or raw_comment.startswith("\t")
                    if is_indented and ":" in comment:
                        pfx, ns = comment.split(":", 1)
                        pfx_clean = pfx.strip()
                        if pfx_clean not in STANDARD_SSSOM_SLOTS:
                            curie_map[pfx_clean] = ns.strip().strip("'\"")
                            continue
                    in_curie_map = False

                if ":" in comment:
                    k, v = comment.split(":", 1)
                    k_clean = k.strip()
                    if k_clean in STANDARD_SSSOM_SLOTS and k_clean != "curie_map":
                        header_meta[k_clean] = v.strip().strip("'\"")
            else:
                in_curie_map = False
                data_lines.append(line)

    for bad_key in STANDARD_SSSOM_SLOTS:
        curie_map.pop(bad_key, None)
    curie_map.pop("source_url", None)

    if curie_map:
        header_meta["curie_map"] = curie_map

    if data_lines:
        reader = csv.DictReader(data_lines, delimiter="\t")
        fieldnames = reader.fieldnames or []
        for row in reader:
            rows.append({k: (v or "") for k, v in row.items()})

    return header_meta, rows, fieldnames


def _write_sssom_tsv(
    path: Path,
    metadata: Dict[str, Any],
    rows: List[Dict[str, Any]],
    fieldnames: Optional[List[str]] = None,
    compress: bool = False,
) -> Path:
    """
    Writes a valid SSSOM TSV file with embedded YAML header comments.
    Supports gzip compression when compress=True or when path ends with .gz.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    is_gz = compress or path.name.lower().endswith(".gz")
    if is_gz and not path.name.lower().endswith(".gz"):
        path = path.with_name(path.name + ".gz")

    # Determine column order: CANONICAL_COLUMN_ORDER first, then others sorted
    all_cols = set()
    for r in rows:
        all_cols.update(r.keys())

    # Build fieldnames
    col_order = []
    for col in CANONICAL_COLUMN_ORDER:
        if col in all_cols or col in MANDATORY_COLUMNS:
            col_order.append(col)
    for col in sorted(all_cols):
        if col not in col_order:
            col_order.append(col)

    if not fieldnames:
        fieldnames = col_order

    # Ensure mapping_date header uses earliest authentic row date if header date is missing or system-generated
    h_m_date = metadata.get("mapping_date")
    if not h_m_date or is_system_date(h_m_date):
        auth_row_dates = [
            str(r.get("mapping_date", "")).strip()
            for r in rows
            if str(r.get("mapping_date", "")).strip() and not is_system_date(r.get("mapping_date"))
        ]
        if auth_row_dates:
            metadata["mapping_date"] = sorted(auth_row_dates)[0]
        elif "mapping_date" in metadata:
            del metadata["mapping_date"]

    # Ensure mapping_set_version header is not a system date
    h_m_ver = metadata.get("mapping_set_version")
    if h_m_ver and is_system_date(h_m_ver):
        del metadata["mapping_set_version"]

    tmp_path = path.with_name(path.name + ".tmp")
    if is_gz:
        fh = gzip.open(tmp_path, "wt", newline="", encoding="utf-8")
    else:
        fh = tmp_path.open("w", newline="", encoding="utf-8")

    with fh:
        # Write curie_map comment block
        curie_map = metadata.get("curie_map", {})
        if curie_map and isinstance(curie_map, dict):
            fh.write("# curie_map:\n")
            for pfx in sorted(curie_map):
                ns = str(curie_map[pfx]).strip().strip("'\"")
                fh.write(f'#   {pfx}: "{ns}"\n')

        # Write core standard SSSOM header comments
        for k in sorted(metadata):
            if k in ("curie_map", "mappings", "review") or k not in STANDARD_SSSOM_SLOTS:
                continue
            val = metadata[k]
            if isinstance(val, (str, int, float, bool)):
                v_str = str(val).strip().strip("'\"")
                if not v_str or v_str.lower() == "none":
                    continue
                if ":" in v_str or "-" in v_str or " " in v_str:
                    clean_v = v_str.replace('"', '\\"')
                    fh.write(f'# {k}: "{clean_v}"\n')
                else:
                    fh.write(f"# {k}: {v_str}\n")

        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: str(r.get(k, "") or "") for k in fieldnames})

    tmp_path.replace(path)
    return path


# --------------------------------------------------------------
# 3️⃣  SMART MERGE LOGIC
# --------------------------------------------------------------

def _merge_headers(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(old)
    for k, v in new.items():
        if k not in merged or not merged[k]:
            merged[k] = v
        elif k == "curie_map" and isinstance(v, dict):
            merged_cmap = dict(merged.get("curie_map", {}))
            merged_cmap.update(v)
            merged["curie_map"] = merged_cmap
        elif isinstance(v, str) and len(v) > len(str(merged[k])):
            merged[k] = v
    return merged


def _merge_rows(
    old_rows: List[Dict[str, Any]],
    new_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Merge mapping rows deduplicating by (subject_id, predicate_id, object_id).
    Respects SSSOM semantics:
    - mapping_justification: single CURIE, manual curation takes precedence
    - multivalued columns: pipe '|' delimited, discarding generic fallback when specific tools exist
    - mapping_date: earliest historical date
    - confidence: max numeric score
    - comment: clean unique clauses
    """
    def _row_key(r: Dict[str, Any]) -> Tuple[str, str, str]:
        return (
            str(r.get("subject_id", "")).strip(),
            str(r.get("predicate_id", "")).strip(),
            str(r.get("object_id", "")).strip(),
        )

    multivalued_cols = {
        "mapping_tool",
        "mapping_tool_version",
        "mapping_provider",
        "author_id",
        "author_label",
        "creator_id",
        "creator_label",
        "reviewer_id",
        "reviewer_label",
        "see_also",
    }

    def _clean_row(row: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(row)
        just = str(d.get("mapping_justification", "")).strip()
        if ";" in just or "|" in just:
            if "ManualMappingCuration" in just:
                d["mapping_justification"] = "semapv:ManualMappingCuration"
            elif "LexicalMatching" in just:
                d["mapping_justification"] = "semapv:LexicalMatching"
            else:
                d["mapping_justification"] = re.split(r"[|;]", just)[0].strip()
        return d

    merged_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for r in old_rows:
        key = _row_key(r)
        if key[0] and key[2]:
            merged_map[key] = _clean_row(r)

    for r in new_rows:
        key = _row_key(r)
        if not key[0] or not key[2]:
            continue

        clean_r = _clean_row(r)
        if key not in merged_map:
            merged_map[key] = clean_r
        else:
            existing = merged_map[key]
            for col, val in clean_r.items():
                if col in ("subject_id", "predicate_id", "object_id"):
                    continue
                v_str = str(val).strip()
                if not v_str:
                    continue
                old_val = str(existing.get(col, "")).strip()
                if not old_val:
                    existing[col] = v_str
                    continue
                if old_val == v_str:
                    continue

                # 1. Mapping Justification (singular CURIE, manual takes precedence)
                if col == "mapping_justification":
                    if "ManualMappingCuration" in old_val or "ManualMappingCuration" in v_str:
                        existing[col] = "semapv:ManualMappingCuration"
                    elif "LexicalMatching" in old_val or "LexicalMatching" in v_str:
                        existing[col] = "semapv:LexicalMatching"
                    else:
                        existing[col] = old_val

                # 2. Multivalued slots (pipe delimited)
                elif col in multivalued_cols:
                    raw_tokens = []
                    for s in (old_val, v_str):
                        for part in re.split(r"[|;]", s):
                            tok = part.strip()
                            if tok:
                                raw_tokens.append(tok)
                    # Discard generic fallback if specific tools exist
                    if col == "mapping_tool" and any(t != "KOS-Mappings Pipeline" for t in raw_tokens):
                        raw_tokens = [t for t in raw_tokens if t != "KOS-Mappings Pipeline"]
                    if col == "mapping_tool_version" and any(t != "1.0.0" for t in raw_tokens):
                        raw_tokens = [t for t in raw_tokens if t != "1.0.0"]
                    # Preserve insertion order deduplication
                    deduped = list(dict.fromkeys(raw_tokens))
                    existing[col] = "|".join(deduped)

                # 3. Mapping date (prefer earliest historical date)
                elif col == "mapping_date":
                    dates = [d.strip() for d in re.split(r"[|;]", f"{old_val};{v_str}") if d.strip()]
                    valid_dates = [d for d in dates if re.match(r"^\d{4}(?:-\d{2}-\d{2})?$", d)]
                    if valid_dates:
                        existing[col] = min(valid_dates)
                    else:
                        existing[col] = old_val

                # 4. Confidence (max numeric score)
                elif col == "confidence":
                    try:
                        scores = [float(s) for s in re.split(r"[|;]", f"{old_val};{v_str}") if s.strip()]
                        max_s = max(scores)
                        existing[col] = "1" if max_s == 1.0 else str(max_s)
                    except ValueError:
                        existing[col] = old_val

                # 5. Comment (cleanly merged clauses)
                elif col == "comment":
                    parts_old = [p.strip() for p in re.split(r"[;]|\.\s+", old_val) if p.strip()]
                    parts_new = [p.strip() for p in re.split(r"[;]|\.\s+", v_str) if p.strip()]
                    all_parts = list(dict.fromkeys(parts_old + parts_new))
                    if any("Mediation Method: Manual" in p for p in all_parts):
                        all_parts = [p for p in all_parts if "Mediation Method: Automatic" not in p]
                # 6. License (prefer specific license over unspecified/CC0-1.0 default)
                elif col == "license":
                    if "unspecified" in old_val.lower() and "unspecified" not in v_str.lower():
                        existing[col] = v_str
                    elif "unspecified" in v_str.lower():
                        existing[col] = old_val
                    elif old_val == "CC0-1.0" and v_str != "CC0-1.0":
                        existing[col] = v_str
                    elif v_str == "CC0-1.0" and old_val != "CC0-1.0":
                        existing[col] = old_val
                    elif old_val != v_str:
                        existing[col] = f"{old_val}|{v_str}"

                # 7. Default scalar: keep the more specific/longer value
                else:
                    if len(v_str) > len(old_val):
                        existing[col] = v_str

    merged_rows = list(merged_map.values())
    all_cols = set()
    for r in merged_rows:
        all_cols.update(r.keys())

    fieldnames = [c for c in CANONICAL_COLUMN_ORDER if c in all_cols or c in MANDATORY_COLUMNS]
    for c in sorted(all_cols):
        if c not in fieldnames:
            fieldnames.append(c)

    return merged_rows, fieldnames


def _infer_prefix_pair(row: Dict[str, Any]) -> Tuple[str, str]:
    subj = str(row.get("subject_id", "")).strip()
    obj = str(row.get("object_id", "")).strip()
    if subj.startswith("#"):
        subj = f"sumo:{subj.lstrip('#')}"
    if obj.startswith("#"):
        obj = f"sumo:{obj.lstrip('#')}"
    p1 = subj.split(":")[0] if ":" in subj else "source"
    p2 = obj.split(":")[0] if ":" in obj else "target"
    p1 = re.sub(r"[^a-zA-Z0-9_\-]", "", p1).lower() or "source"
    p2 = re.sub(r"[^a-zA-Z0-9_\-]", "", p2).lower() or "target"
    if "recommendat" in p1 or len(p1) > 30:
        p1 = "source"
    if "recommendat" in p2 or len(p2) > 30:
        p2 = "target"
    return p1, p2


# --------------------------------------------------------------
# 4️⃣  CORE ENTRY POINT
# --------------------------------------------------------------

def write_sssom_file(
    input_location: Optional[str] = None,
    *,
    yes: bool = False,
    no_edit: bool = False,
    output_override: Optional[str] = None,
    compress: bool = False,
) -> List[Path]:
    """
    Process input_location into reviewed SSSOM mappings,
    write/merge into canonical ./commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv (or .sssom.tsv.gz),
    and optionally write to output_override.
    Returns list of written file paths.
    """
    if input_location is None:
        LOGGER.info("No input file/URL supplied – launching manual entry.")
        subprocess.run(
            [sys.executable, str(_SRC_DIR / "load_from_manual_input.py")],
            check=True,
        )
        input_location = "manual.sssom.tsv"

    if isinstance(input_location, dict):
        metadata = dict(input_location)
    elif isinstance(input_location, (str, Path)) and str(input_location).lower().endswith(".json") and Path(input_location).is_file():
        with open(input_location, "r", encoding="utf-8") as jf:
            metadata = json.load(jf)
    else:
        LOGGER.info("Reviewing SSSOM metadata for %s", input_location)
        metadata = _run_review_script(str(input_location), yes=yes, no_edit=no_edit)

    rows = metadata.get("mappings", [])
    if not rows and isinstance(input_location, (str, Path)):
        # Fallback to direct loader
        LOGGER.warning("Metadata contained no mapping rows, falling back to loader.")
        from src.generate_sssom_metadata import generate_metadata
        doc = generate_metadata(str(input_location))
        rows = doc.get("mappings", [])
        if "curie_map" in doc:
            metadata.setdefault("curie_map", {}).update(doc["curie_map"])

    if not rows:
        raise RuntimeError(f"No mapping rows were found in {input_location} – nothing to write.")

    # Clean rows: ensure mandatory columns and strip fragment/relative prefixes
    clean_rows = []
    for r in rows:
        row_dict = dict(r)
        if not row_dict.get("mapping_justification"):
            row_dict["mapping_justification"] = "semapv:ManualMappingCuration"
        s_id = str(row_dict.get("subject_id", "")).strip()
        o_id = str(row_dict.get("object_id", "")).strip()
        if s_id.startswith("#"):
            s_id = s_id.lstrip("#")
        if o_id.startswith("#"):
            o_id = o_id.lstrip("#")
        if ":" not in s_id and s_id:
            s_id = f"sumo:{s_id}"
        if ":" not in o_id and o_id:
            o_id = f"sumo:{o_id}"
        row_dict["subject_id"] = s_id
        row_dict["object_id"] = o_id
        clean_rows.append(row_dict)

    written_paths: List[Path] = []
    commons_root = _ROOT_DIR / "commons"

    # Group mappings by prefix pair
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in clean_rows:
        pair = _infer_prefix_pair(r)
        groups[pair].append(r)

    # 1. Write or merge canonical files into ./commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv (or .gz)
    for (p1, p2), group_rows in groups.items():
        canonical_tsv = commons_root / p1 / p2 / f"{p1}_{p2}.sssom.tsv"
        canonical_gz = commons_root / p1 / p2 / f"{p1}_{p2}.sssom.tsv.gz"

        existing_path = canonical_gz if canonical_gz.is_file() else (canonical_tsv if canonical_tsv.is_file() else None)
        target_compressed = compress or (existing_path == canonical_gz) or (len(group_rows) > 50000)
        target_path = canonical_gz if target_compressed else canonical_tsv

        group_meta = dict(metadata)
        group_meta["mapping_set_id"] = f"https://w3id.org/commons/mappings/{p1}_{p2}"
        group_meta["mapping_set_title"] = f"{p1.upper()} to {p2.upper()} Mappings"

        # Attach structure and version metadata
        version_meta = _resolve_structure_metadata(p1, p2, group_rows, group_meta)
        group_meta.update(version_meta)

        # Enrich incoming rows with full metadata attributes
        enriched_group_rows = _enrich_row_metadata(group_rows, group_meta, p1, p2)
        # Deduplicate and merge rows within incoming group
        merged_group_rows, group_fieldnames = _merge_rows([], enriched_group_rows)

        if existing_path:
            old_meta, old_rows, _ = _read_sssom_tsv(existing_path)
            merged_meta = _merge_headers(old_meta, group_meta)
            # Re-enrich existing rows to ensure complete row metadata consistency across the totality
            enriched_old_rows = _enrich_row_metadata(old_rows, merged_meta, p1, p2)
            merged_rows, fieldnames = _merge_rows(enriched_old_rows, merged_group_rows)
            # Filter curie map to strictly include only entities mapped in this file
            merged_meta["curie_map"] = _filter_curie_map(
                merged_meta.get("curie_map", {}), merged_rows, merged_meta, p1=p1, p2=p2
            )
            written_file = _write_sssom_tsv(target_path, merged_meta, merged_rows, fieldnames, compress=target_compressed)
            if existing_path != target_path and existing_path.is_file():
                existing_path.unlink()
            LOGGER.info("Merged %d rows into canonical file: %s", len(merged_rows), written_file)
        else:
            # Filter curie map to strictly include only entities mapped in this file
            group_meta["curie_map"] = _filter_curie_map(
                group_meta.get("curie_map", {}), merged_group_rows, group_meta, p1=p1, p2=p2
            )
            written_file = _write_sssom_tsv(target_path, group_meta, merged_group_rows, group_fieldnames, compress=target_compressed)
            LOGGER.info("Wrote %d rows to new canonical file: %s", len(merged_group_rows), written_file)

        written_paths.append(written_file)

    # 2. If output_override was specified, write all rows to that file
    if output_override:
        override_path = Path(output_override).resolve()
        override_meta = dict(metadata)
        if override_meta.get("mapping_set_version") and is_system_date(override_meta["mapping_set_version"]):
            del override_meta["mapping_set_version"]
        if not override_meta.get("mapping_tool"):
            override_meta["mapping_tool"] = "KOS-Mappings Pipeline"
        if not override_meta.get("mapping_tool_version"):
            override_meta["mapping_tool_version"] = "1.0.0"

        enriched_override_rows = []
        for r in clean_rows:
            p1_r, p2_r = _infer_prefix_pair(r)
            enriched_override_rows.extend(_enrich_row_metadata([r], override_meta, p1_r, p2_r))

        override_meta["curie_map"] = _filter_curie_map(
            override_meta.get("curie_map", {}), enriched_override_rows, override_meta
        )
        is_override_gz = compress or override_path.name.lower().endswith(".gz")
        written_override = _write_sssom_tsv(override_path, override_meta, enriched_override_rows, compress=is_override_gz)
        LOGGER.info("Wrote full SSSOM file to output override: %s", written_override)
        written_paths.append(written_override)

    print(f"\n✅ SSSOM processing complete. Output written to {len(written_paths)} location(s).")
    return written_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write and merge SSSOM mappings into canonical commons registry structure."
    )
    parser.add_argument("input", nargs="?", default=None, help="Path or URL to mapping file.")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-accept metadata review.")
    parser.add_argument("--no-edit", action="store_true", help="Skip opening metadata editor.")
    parser.add_argument("-o", "--output", default=None, help="Explicit output file path override.")
    parser.add_argument("-c", "--compress", action="store_true", help="Gzip compress output SSSOM files (.sssom.tsv.gz).")
    args = parser.parse_args()

    try:
        write_sssom_file(
            args.input,
            yes=args.yes,
            no_edit=args.no_edit,
            output_override=args.output,
            compress=args.compress,
        )
    except Exception as exc:
        LOGGER.exception("An error occurred: %s", exc)
        sys.exit(1)
        LOGGER.exception("An error occurred: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()