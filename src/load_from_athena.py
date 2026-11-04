#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
load_from_athena.py
-------------------
Loader for OHDSI Athena (OMOP CDM v5) vocabulary archives.
Parses CONCEPT.csv, CONCEPT_RELATIONSHIP.csv, and VOCABULARY.csv directly
from ZIP archives or extracted directories, normalizes entities into CURIEs,
maps Athena relationships to standard SSSOM/SKOS predicates, and builds
SSSOM mapping datasets.
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

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

LOGGER = logging.getLogger(__name__)

ATHENA_VOCAB_PREFIX_MAP: Dict[str, str] = {
    "snomed": "snomedct",
    "loinc": "loinc",
    "ucum": "ucum",
    "omop extension": "omopext",
    "omop concept class": "omopclass",
    "osm": "osm",
    "us census": "uscensus",
    "icd10": "icd10",
    "icd10cm": "icd10cm",
    "icd9cm": "icd9cm",
    "rxnorm": "rxnorm",
    "rxnorm extension": "rxnormext",
    "mesh": "mesh",
    "cpt4": "cpt",
    "hcpcs": "hcpcs",
    "ndc": "ndc",
    "atc": "atc",
    "meddra": "meddra",
    "ncit": "ncit",
    "sopt": "sopt",
    "hpo": "hp",
    "mondo": "mondo",
    "icd9proc": "icd9proc",
    "icd10pcs": "icd10pcs",
    "icd10gm": "icd10gm",
    "orphacode": "orphanet",
    "episode": "omopepisode",
    "visit": "omopvisit",
}

ATHENA_PREFIX_URLS: Dict[str, str] = {
    "snomedct": "http://snomed.info/id/",
    "loinc": "https://loinc.org/",
    "ucum": "http://unitsofmeasure.org/",
    "omopext": "https://athena.ohdsi.org/search-terms/terms/",
    "osm": "https://www.openstreetmap.org/",
    "uscensus": "https://www.census.gov/",
    "icd10": "https://icd.who.int/browse10/2019/en#/",
    "icd10cm": "https://identifiers.org/icd10cm:",
    "icd9cm": "https://identifiers.org/icd9cm:",
    "icd9proc": "https://identifiers.org/icd9proc:",
    "icd10pcs": "https://identifiers.org/icd10pcs:",
    "icd10gm": "https://identifiers.org/icd10gm:",
    "rxnorm": "https://identifiers.org/rxnorm:",
    "mesh": "http://id.nlm.nih.gov/mesh/",
    "ncit": "http://purl.obolibrary.org/obo/NCIT_",
    "hp": "http://purl.obolibrary.org/obo/HP_",
    "mondo": "http://purl.obolibrary.org/obo/MONDO_",
    "orphanet": "http://www.orpha.net/ORDO/Orphanet_",
    "meddra": "https://identifiers.org/meddra:",
    "cpt": "https://identifiers.org/cpt:",
    "hcpcs": "https://identifiers.org/hcpcs:",
    "atc": "https://identifiers.org/atc:",
    "ndc": "https://identifiers.org/ndc:",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "semapv": "https://w3id.org/semapv/vocab/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "sssom": "https://w3id.org/sssom/",
    "dcterms": "http://purl.org/dc/terms/",
}

ATHENA_RELATIONSHIP_PREDICATE_MAP: Dict[str, str] = {
    "maps to": "skos:exactMatch",
    "mapped from": "skos:exactMatch",
    "is a": "skos:broadMatch",
    "subsumes": "skos:narrowMatch",
    "concept replaced by": "sssom:has_exact_replacement",
    "concept replaces": "dcterms:replaces",
    "concept same_as to": "owl:sameAs",
    "concept was_a to": "skos:broadMatch",
    "maps to value": "skos:relatedMatch",
    "value mapped from": "skos:relatedMatch",
    "precoord pair of": "skos:relatedMatch",
    "has precoord pair": "skos:relatedMatch",
}


def normalize_vocab_prefix(vocab_id: str) -> str:
    """Normalize OMOP Athena vocabulary identifier to canonical lowercase CURIE prefix."""
    if not vocab_id:
        return "omop"
    key = vocab_id.strip().lower()
    if key in ATHENA_VOCAB_PREFIX_MAP:
        return ATHENA_VOCAB_PREFIX_MAP[key]
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "", key)
    return clean or "omop"


def normalize_relationship_predicate(rel_id: str) -> str:
    """Map OMOP relationship ID to standard SSSOM / SKOS predicate."""
    if not rel_id:
        return "skos:relatedMatch"
    key = rel_id.strip().lower()
    return ATHENA_RELATIONSHIP_PREDICATE_MAP.get(key, "skos:relatedMatch")


def format_athena_date(raw_date: Optional[str]) -> Optional[str]:
    """Convert Athena integer dates (YYYYMMDD) to ISO format (YYYY-MM-DD), filtering out epoch placeholders."""
    if not raw_date:
        return None
    d = str(raw_date).strip()
    if len(d) == 8 and d.isdigit():
        if d == "19700101":
            return None  # Unix epoch placeholder used by OMOP when original date is untracked
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d
    return None


class AthenaReader:
    """Streaming reader for Athena ZIP archives or extracted OMOP vocabulary directories."""

    def __init__(self, source_path: Union[str, Path]):
        self.path = Path(source_path)
        self.is_zip = self.path.is_file() and self.path.suffix.lower() == ".zip"
        if not self.path.exists():
            raise FileNotFoundError(f"Athena source not found: {self.path}")

    def open_table(self, table_name: str) -> Tuple[Any, Any]:
        """Returns (file_handle, is_zip_context). Must be closed by caller."""
        csv_name = f"{table_name}.csv"
        if self.is_zip:
            z = zipfile.ZipFile(self.path, "r")
            # Find matching file case-insensitively
            match = None
            for name in z.namelist():
                if Path(name).name.lower() == csv_name.lower():
                    match = name
                    break
            if not match:
                z.close()
                raise FileNotFoundError(f"Table '{csv_name}' not found in archive {self.path}")
            raw_f = z.open(match, "r")
            text_f = io.TextIOWrapper(raw_f, encoding="utf-8", errors="replace")
            return text_f, (z, raw_f)
        else:
            p = self.path / csv_name
            if not p.is_file():
                for cand in self.path.glob("*.csv"):
                    if cand.name.lower() == csv_name.lower():
                        p = cand
                        break
            if not p.is_file():
                raise FileNotFoundError(f"Table '{csv_name}' not found in {self.path}")
            text_f = open(p, "r", encoding="utf-8", errors="replace")
            return text_f, None

    def read_vocabularies(self) -> Dict[str, Dict[str, str]]:
        """Reads VOCABULARY.csv returning dict of vocab_id -> {vocabulary_name, vocabulary_version}."""
        vocabs = {}
        try:
            fh, ctx = self.open_table("VOCABULARY")
            try:
                reader = csv.DictReader(fh, delimiter="\t")
                for row in reader:
                    vocabs[row["vocabulary_id"]] = {
                        "name": row.get("vocabulary_name", ""),
                        "version": row.get("vocabulary_version", "") or "",
                    }
            finally:
                fh.close()
                if ctx:
                    ctx[1].close()
                    ctx[0].close()
        except FileNotFoundError:
            LOGGER.warning("VOCABULARY.csv not found in Athena archive.")
        return vocabs

    def read_concepts(
        self,
        target_vocab_ids: Optional[Set[str]] = None,
    ) -> Dict[str, Tuple[str, str, str]]:
        """
        Reads CONCEPT.csv returning concept_id -> (vocabulary_id, concept_code, concept_name).
        If target_vocab_ids is specified, only keeps concepts matching those vocabularies to save RAM.
        """
        concepts = {}
        target_lower = {v.strip().lower() for v in target_vocab_ids} if target_vocab_ids else None
        fh, ctx = self.open_table("CONCEPT")
        try:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                v_id = row.get("vocabulary_id", "")
                if target_lower and v_id.strip().lower() not in target_lower:
                    continue
                c_id = row["concept_id"]
                concepts[c_id] = (v_id, row.get("concept_code", ""), row.get("concept_name", ""))
        finally:
            fh.close()
            if ctx:
                ctx[1].close()
                ctx[0].close()
        return concepts

    def inspect_pairs(self, limit_rows: Optional[int] = None) -> List[Tuple[str, str, str, int]]:
        """
        Scans CONCEPT and CONCEPT_RELATIONSHIP to list available (vocab_1, vocab_2, relationship_id)
        with row counts.
        """
        LOGGER.info("Reading concepts for pairing inspection...")
        concepts = self.read_concepts()
        counts = Counter()
        LOGGER.info("Scanning relationships...")
        fh, ctx = self.open_table("CONCEPT_RELATIONSHIP")
        try:
            reader = csv.DictReader(fh, delimiter="\t")
            for i, row in enumerate(reader):
                if limit_rows and i >= limit_rows:
                    break
                if row.get("invalid_reason"):
                    continue
                c1 = concepts.get(row.get("concept_id_1"))
                c2 = concepts.get(row.get("concept_id_2"))
                if c1 and c2:
                    counts[(c1[0], c2[0], row.get("relationship_id", ""))] += 1
        finally:
            fh.close()
            if ctx:
                ctx[1].close()
                ctx[0].close()

        res = []
        for (v1, v2, rel), cnt in counts.most_common():
            res.append((v1, v2, rel, cnt))
        return res


def load(
    source: str,
    *,
    pairs: Optional[Union[str, List[str], Set[str]]] = None,
    relationships: Optional[Union[str, List[str], Set[str]]] = None,
    include_intra: bool = False,
    exclude_invalid: bool = True,
    limit: Optional[int] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Parse an Athena export archive or directory and return an SSSOM document dict.

    Parameters:
    -----------
    source : str
        Path to Athena ZIP or directory.
    pairs : str or collection of str, optional
        Pairs of vocabularies to extract, e.g. ["loinc_snomedct", "snomedct_ucum"]
        or comma-delimited string.
    relationships : str or collection of str, optional
        Filter on OMOP relationship_id, e.g. ["Maps to", "Is a", "Concept replaced by"].
        Defaults to standard mapping relationships ("Maps to", "Is a", "Concept replaced by").
    include_intra : bool, default False
        Whether to include intra-vocabulary alignments (e.g. snomedct_snomedct replacement).
    exclude_invalid : bool, default True
        Whether to skip rows with an invalid_reason.
    limit : int, optional
        Maximum number of mapping rows to return.
    """
    reader = AthenaReader(source)
    vocab_meta = reader.read_vocabularies()

    # Parse requested pairs
    allowed_pairs: Optional[Set[Tuple[str, str]]] = None
    target_vocab_ids: Optional[Set[str]] = None

    if pairs:
        if isinstance(pairs, str):
            pair_items = [p.strip() for p in re.split(r"[,;|\s]+", pairs) if p.strip()]
        else:
            pair_items = list(pairs)

        allowed_pairs = set()
        target_vocab_ids = set()
        for p in pair_items:
            parts = re.split(r"[:_-]", p.lower())
            if len(parts) >= 2:
                p1, p2 = parts[0], parts[1]
                allowed_pairs.add((p1, p2))
                # Add potential Athena vocab IDs
                for athena_v, norm_v in ATHENA_VOCAB_PREFIX_MAP.items():
                    if norm_v == p1:
                        target_vocab_ids.add(athena_v)
                        target_vocab_ids.add(athena_v.upper())
                    if norm_v == p2:
                        target_vocab_ids.add(athena_v)
                        target_vocab_ids.add(athena_v.upper())

    # Parse allowed relationships
    allowed_rels: Optional[Set[str]] = None
    if relationships:
        if isinstance(relationships, str):
            rel_items = [r.strip() for r in re.split(r"[,;|]+", relationships) if r.strip()]
        else:
            rel_items = list(relationships)
        allowed_rels = {r.strip().lower() for r in rel_items}
    else:
        # Default meaningful mappings
        allowed_rels = {"maps to", "is a", "concept replaced by"}

    LOGGER.info("Loading concepts from Athena archive...")
    concepts = reader.read_concepts(target_vocab_ids=target_vocab_ids if (target_vocab_ids and len(target_vocab_ids) > 0) else None)
    LOGGER.info("Loaded %d concepts.", len(concepts))

    curie_map = dict(ATHENA_PREFIX_URLS)
    mappings: List[Dict[str, Any]] = []

    LOGGER.info("Streaming CONCEPT_RELATIONSHIP.csv...")
    fh, ctx = reader.open_table("CONCEPT_RELATIONSHIP")
    try:
        r_reader = csv.DictReader(fh, delimiter="\t")
        for row in r_reader:
            if exclude_invalid and row.get("invalid_reason"):
                continue

            rel_raw = row.get("relationship_id", "")
            if allowed_rels and rel_raw.strip().lower() not in allowed_rels:
                continue

            c1 = concepts.get(row.get("concept_id_1"))
            c2 = concepts.get(row.get("concept_id_2"))
            if not c1 or not c2:
                continue

            v1_raw, code1, name1 = c1
            v2_raw, code2, name2 = c2

            pfx1 = normalize_vocab_prefix(v1_raw)
            pfx2 = normalize_vocab_prefix(v2_raw)

            if not include_intra and pfx1 == pfx2:
                continue

            if allowed_pairs:
                if (pfx1, pfx2) not in allowed_pairs and (pfx1.lower(), pfx2.lower()) not in allowed_pairs:
                    continue

            # Ensure prefixes in curie_map
            if pfx1 not in curie_map:
                curie_map[pfx1] = f"https://identifiers.org/{pfx1}:"
            if pfx2 not in curie_map:
                curie_map[pfx2] = f"https://identifiers.org/{pfx2}:"

            predicate = normalize_relationship_predicate(rel_raw)

            # Mapping justification
            if rel_raw.strip().lower() == "maps to":
                justification = "semapv:ManualMappingCuration"
            elif rel_raw.strip().lower() == "is a":
                justification = "semapv:ManualMappingCuration"
            elif rel_raw.strip().lower() == "concept replaced by":
                justification = "semapv:ManualMappingCuration"
            else:
                justification = "semapv:UnspecifiedMatching"

            # Date handling
            m_date = format_athena_date(row.get("valid_start_date"))
            if not m_date:
                # Fall back to vocab release version if it has a date
                v_ver = vocab_meta.get(v1_raw, {}).get("version", "")
                m_match = re.search(r"\b(20\d\d[-_]\d{2}(?:[-_]\d{2})?)\b", v_ver)
                if m_match:
                    m_date = m_match.group(1).replace("_", "-")

            # Extract source versions
            s_ver = vocab_meta.get(v1_raw, {}).get("version", "")
            o_ver = vocab_meta.get(v2_raw, {}).get("version", "")

            mapping_row: Dict[str, Any] = {
                "subject_id": f"{pfx1}:{code1}",
                "predicate_id": predicate,
                "object_id": f"{pfx2}:{code2}",
                "mapping_justification": justification,
                "subject_label": name1,
                "object_label": name2,
                "subject_source": pfx1,
                "subject_source_version": s_ver,
                "object_source": pfx2,
                "object_source_version": o_ver,
                "mapping_tool": "Athena OHDSI",
                "mapping_tool_version": "v5.0",
                "mapping_provider": "https://athena.ohdsi.org/",
                "license": "https://w3id.org/sssom/license/unspecified",
                "comment": f"OMOP relationship_id: {rel_raw}",
            }
            if m_date:
                mapping_row["mapping_date"] = m_date

            mappings.append(mapping_row)
            if limit and len(mappings) >= limit:
                break
    finally:
        fh.close()
        if ctx:
            ctx[1].close()
            ctx[0].close()

    LOGGER.info("Extracted %d SSSOM mapping rows from Athena.", len(mappings))

    first_pair = ("athena", "mappings")
    if mappings:
        first_s = mappings[0]["subject_id"].split(":")[0]
        first_o = mappings[0]["object_id"].split(":")[0]
        first_pair = (first_s, first_o)

    doc: Dict[str, Any] = {
        "mapping_set_id": f"https://w3id.org/commons/mappings/{first_pair[0]}_{first_pair[1]}",
        "mapping_set_title": f"{first_pair[0].upper()} to {first_pair[1].upper()} Mappings",
        "mapping_provider": "https://athena.ohdsi.org/",
        "mapping_tool": "Athena OHDSI",
        "mapping_tool_version": "v5.0",
        "license": "https://w3id.org/sssom/license/unspecified",
        "curie_map": curie_map,
        "mappings": mappings,
    }

    # Derive mapping_date from earliest row date
    row_dates = [r["mapping_date"] for r in mappings if r.get("mapping_date")]
    if row_dates:
        doc["mapping_date"] = sorted(row_dates)[0]

    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest and parse OHDSI Athena vocabulary downloads into SSSOM.")
    parser.add_argument("source", help="Path to Athena ZIP file or extracted directory.")
    parser.add_argument("--list-pairs", action="store_true", help="Inspect and list available vocabulary pairs and counts.")
    parser.add_argument("--pair", action="append", help="Filter for specific vocabulary pair (e.g. loinc:snomedct). Can be repeated.")
    parser.add_argument("--rel", action="append", help="Filter for specific relationship_id (e.g. 'Maps to'). Can be repeated.")
    parser.add_argument("--include-intra", action="store_true", help="Include intra-vocabulary mappings (e.g. snomedct to snomedct).")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of mappings extracted.")
    parser.add_argument("--write-commons", action="store_true", help="Automatically partition and write into ./commons/.")
    parser.add_argument("-c", "--compress", action="store_true", help="Gzip compress output SSSOM files (.sssom.tsv.gz).")
    parser.add_argument("-o", "--output", help="Optional specific output SSSOM TSV path.")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.list_pairs:
        reader = AthenaReader(args.source)
        pairs = reader.inspect_pairs()
        print(f"\nDiscovered {len(pairs)} vocabulary/relationship combinations in Athena:")
        print(f"{'Subject Vocab':<20} {'Object Vocab':<20} {'Relationship':<25} {'Count':>10}")
        print("-" * 80)
        for v1, v2, rel, cnt in pairs[:50]:
            print(f"{v1:<20} {v2:<20} {rel:<25} {cnt:>10,}")
        return

    doc = load(
        args.source,
        pairs=args.pair,
        relationships=args.rel,
        include_intra=args.include_intra,
        limit=args.limit,
    )

    print(f"Loaded {len(doc['mappings'])} mappings.")

    if args.write_commons:
        from src.write_sssom_file import write_sssom_file
        written = write_sssom_file(doc, yes=True, no_edit=True, compress=args.compress)
        print(f"Successfully wrote {len(written)} SSSOM files to Mapping Commons:")
        for p in written:
            print(f"  {p}")
    elif args.output:
        from src.write_sssom_file import _write_sssom_tsv
        out_p = Path(args.output)
        _write_sssom_tsv(out_p, doc, doc["mappings"], compress=args.compress)
        print(f"Wrote SSSOM TSV to {out_p}")


if __name__ == "__main__":
    main()
