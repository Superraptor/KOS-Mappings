#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
load_from_webpage.py
--------------------
Extracts ontological mappings from HTML tables and web pages into SSSOM format.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

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
    "dcat": "http://www.w3.org/ns/dcat#",
    "dcatap": "http://data.europa.eu/r5r/",
    "schema": "http://schema.org/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "vcard": "http://www.w3.org/2006/vcard/ns#",
    "adms": "http://www.w3.org/ns/adms#",
    "bfo": "http://www.ifomis.org/bfo/1.1#",
    "gfo": "http://www.onto-med.de/ontologies/gfo.owl#",
    "dolce": "http://www.loa-cnr.it/ontologies/DOLCE-Lite.owl#",
    "ro": "http://purl.org/obo/owl/OBO_REL#",
    "temporalrelations": "http://www.loa-cnr.it/ontologies/TemporalRelations.owl#",
    "spatialrelations": "http://www.loa-cnr.it/ontologies/SpatialRelations.owl#",
    "functionalparticipation": "http://www.loa-cnr.it/ontologies/FunctionalParticipation.owl#",
    "datacite": "http://datacite.org/schema/kernel-4/",
}

ROMULUS_VERSIONS = {
    "bfo": "1.1",
    "gfo": "1.0",
    "dolce": "397",
    "ro": "1.0",
    "temporalrelations": "1.0",
    "spatialrelations": "1.0",
    "functionalparticipation": "1.0",
}

URI_SYNONYMS = {
    "http://www.ifomis.org/bfo/1.1/snap#": ("bfo", "http://www.ifomis.org/bfo/1.1#"),
    "http://www.ifomis.org/bfo/1.1/span#": ("bfo", "http://www.ifomis.org/bfo/1.1#"),
    "http://www.onto-med.de/ontologies/gfo-basic.owl#": ("gfo", "http://www.onto-med.de/ontologies/gfo.owl#"),
    "http://www.obofoundry.org/ro/ro.owl#": ("ro", "http://purl.org/obo/owl/OBO_REL#"),
}


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _normalize_web_url(url: str) -> str:
    """If Wayback URL is missing id_ (raw mode), add id_ to prevent rate-limiting."""
    m = re.match(r"(https?://web\.archive\.org/web/\d{14})(?!id_)(/.*)", url)
    if m:
        return f"{m.group(1)}id_{m.group(2)}"
    return url


def _parse_romulus_tool(tool_str: str) -> Tuple[str, str]:
    """
    Break apart ROMULUS tool names and versions.
    E.g.: 'YAM++ v1.0, PROMPT v3.0' -> ('YAM++|PROMPT', '1.0|3.0')
    """
    tool_str = (tool_str or "").strip()
    if not tool_str or tool_str == "-":
        return "ROMULUS Mediation Framework", "1.0"
    matches = re.findall(r"([A-Za-z0-9\+\-]+)\s+v?(\d+(?:\.\d+)*)", tool_str)
    if matches:
        tools = [m[0].strip() for m in matches]
        versions = [m[1].strip() for m in matches]
        return "|".join(tools), "|".join(versions)
    tools = [t.strip() for t in tool_str.split(",") if t.strip()]
    return "|".join(tools), "1.0"


def _fetch_html(source: str) -> str:
    if _is_url(source):
        source = _normalize_web_url(source)
        LOGGER.info("Fetching HTML from %s", source)
        headers = {"User-Agent": "curl/7.68.0"}
        resp = requests.get(source, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.content.decode("utf-8", errors="replace")
    else:
        path = Path(source)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


def _uri_to_curie(uri: str, prefixes: Dict[str, str]) -> str:
    uri = uri.strip().strip("<>\"'")
    if not uri.startswith(("http://", "https://")):
        return uri

    for syn_ns, (pfx, canonical_ns) in URI_SYNONYMS.items():
        if uri.startswith(syn_ns):
            prefixes[pfx] = canonical_ns
            return f"{pfx}:{uri[len(syn_ns):]}"

    for pfx, ns in prefixes.items():
        if uri.startswith(ns):
            return f"{pfx}:{uri[len(ns):]}"

    try:
        ns, ident = rdflib_split(uri)
        slug = re.sub(r"[^a-zA-Z0-9]", "", Path(urllib.parse.urlparse(ns).path).name or "ns")
        if slug:
            prefixes[slug] = ns
            return f"{slug}:{ident}"
    except Exception:
        pass
    return uri


def rdflib_split(uri: str) -> Tuple[str, str]:
    if "#" in uri:
        parts = uri.rsplit("#", 1)
        return parts[0] + "#", parts[1]
    parts = uri.rsplit("/", 1)
    return parts[0] + "/", parts[1]


def _extract_tables(soup: BeautifulSoup) -> List[List[List[str]]]:
    """Extract 2D text matrix for all tables."""
    extracted = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [re.sub(r"\s+", " ", td.get_text(strip=True)) for td in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(cells)
        if rows:
            extracted.append(rows)
    return extracted


def load(source: str, **kwargs: Any) -> Dict[str, Any]:
    """
    Extract SSSOM mappings from a webpage or HTML document.
    """
    html = _fetch_html(source)
    soup = BeautifulSoup(html, "html.parser")
    tables = _extract_tables(soup)

    curie_map = dict(DEFAULT_PREFIXES)
    mappings: List[Dict[str, Any]] = []

    # 1. Look for Prefix table (e.g., Table with 'Prefix', 'Namespace URI')
    for table in tables:
        if len(table) > 1 and len(table[0]) >= 2:
            h0, h1 = table[0][0].lower(), table[0][1].lower()
            if "prefix" in h0 and ("namespace" in h1 or "uri" in h1):
                for row in table[1:]:
                    if len(row) >= 2 and row[0] and row[1]:
                        curie_map[row[0].strip().rstrip(":")] = row[1].strip()

    # 2. Extract mappings from tables
    for table in tables:
        if len(table) < 2:
            continue

        header = [c.lower() for c in table[0]]

    # ROMULUS alignment index handling: if source is ontologyAlignmentMetadata.html, recurse over all pages
    if "ontologyalignmentmetadata" in source.lower():
        LOGGER.info("Detected ROMULUS alignment index page. Processing all alignment metadata pages.")
        sub_links = []
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if "MediationMetadata" in href and href.endswith(".php"):
                sub_links.append(href)
        LOGGER.info("Found %d ROMULUS alignment metadata sub-pages", len(sub_links))
        all_mappings: List[Dict[str, Any]] = []
        for link in sub_links:
            fname = link.split("/")[-1]
            sub_url = f"https://web.archive.org/web/20180102005419id_/http://www.thezfiles.co.za/ROMULUS/{link}"
            local_cache = Path("downloads/romulus") / fname
            sub_src = str(local_cache) if local_cache.exists() and local_cache.stat().st_size > 500 else sub_url
            try:
                sub_res = load(sub_src)
                curie_map.update(sub_res.get("curie_map", {}))
                for m in sub_res.get("mappings", []):
                    if not m.get("mapping_provider"):
                        m["mapping_provider"] = sub_url
                    all_mappings.append(m)
            except Exception as e:
                LOGGER.warning("Could not process ROMULUS sub-page %s: %s", fname, e)
        return {
            "curie_map": curie_map,
            "mappings": all_mappings,
        }

    # 2. Extract mappings from tables
    for table in tables:
        if len(table) < 2:
            continue

        header = [c.lower() for c in table[0]]

        # ROMULUS format: 'Entity URI', 'Relation', 'Entity URI'
        if any("entity" in h and "uri" in h for h in header) and any("relation" in h for h in header):
            uri_indices = [i for i, h in enumerate(header) if "entity" in h and "uri" in h]
            rel_idx = next(i for i, h in enumerate(header) if "relation" in h)
            map_idx = next((i for i, h in enumerate(header) if "mappable" in h), None)
            inc_idx = next((i for i, h in enumerate(header) if "inconsistency" in h), None)
            date_idx = next((i for i, h in enumerate(header) if "date" in h), None)
            meth_idx = next((i for i, h in enumerate(header) if "method" in h), None)
            tool_idx = next((i for i, h in enumerate(header) if "tool" in h), None)
            creator_idx = next((i for i, h in enumerate(header) if "creator" in h), None)

            if len(uri_indices) >= 2:
                u1_idx, u2_idx = uri_indices[0], uri_indices[1]
                for row in table[1:]:
                    if len(row) <= max(u1_idx, u2_idx, rel_idx):
                        continue
                    u1 = row[u1_idx].strip()
                    u2 = row[u2_idx].strip()
                    rel = row[rel_idx].strip()
                    mappable = row[map_idx].strip() if map_idx is not None and len(row) > map_idx else "Yes"
                    inconsistency = row[inc_idx].strip() if inc_idx is not None and len(row) > inc_idx else "-"
                    date = row[date_idx].strip() if date_idx is not None and len(row) > date_idx else "2012-11-21"
                    method = row[meth_idx].strip() if meth_idx is not None and len(row) > meth_idx else "Manual"
                    tool = row[tool_idx].strip() if tool_idx is not None and len(row) > tool_idx else "-"
                    creator = row[creator_idx].strip() if creator_idx is not None and len(row) > creator_idx else "Zubeida Khan: zkhan@csir.co.za"

                    # Clean entity text (strip (subclass), (superclass))
                    clean_u1 = re.sub(r"\s*\((?:subclass|superclass)\)\s*", "", u1)
                    clean_u2 = re.sub(r"\s*\((?:subclass|superclass)\)\s*", "", u2)
                    if not clean_u1 or not clean_u2 or clean_u1 == clean_u2:
                        continue

                    # Predicate determination
                    if mappable.lower() == "no":
                        pred = "skos:closeMatch"
                    elif "equiv" in rel.lower():
                        pred = "owl:equivalentClass"
                    elif "subsum" in rel.lower():
                        pred = "rdfs:subClassOf"
                    else:
                        pred = "skos:exactMatch"

                    s_curie = _uri_to_curie(clean_u1, curie_map)
                    o_curie = _uri_to_curie(clean_u2, curie_map)
                    if not s_curie or not o_curie or s_curie == o_curie:
                        continue

                    s_pfx = s_curie.split(":")[0] if ":" in s_curie else ""
                    o_pfx = o_curie.split(":")[0] if ":" in o_curie else ""

                    # Creator metadata with mailto: prefix
                    author_id = "mailto:zkhan@csir.co.za"
                    author_label = "Zubeida Khan"
                    if ":" in creator:
                        parts = creator.split(":", 1)
                        author_label = parts[0].strip()
                        raw_email = parts[1].strip()
                        author_id = f"mailto:{raw_email}" if not raw_email.startswith("mailto:") else raw_email
                    elif "@" in creator:
                        author_id = f"mailto:{creator.strip()}"

                    # Justification
                    just = "semapv:ManualMappingCuration" if ("manual" in method.lower() or mappable.lower() == "no" or inconsistency != "-") else "semapv:LexicalMatching"

                    # Mapping tool and version
                    mapping_tool, mapping_tool_version = _parse_romulus_tool(tool)

                    m = {
                        "subject_id": s_curie,
                        "predicate_id": pred,
                        "object_id": o_curie,
                        "mapping_justification": just,
                        "mapping_date": date if date != "-" else "2012-11-21",
                        "author_id": author_id,
                        "author_label": author_label,
                        "creator_id": author_id,
                        "creator_label": author_label,
                        "mapping_tool": mapping_tool,
                        "mapping_tool_version": mapping_tool_version,
                        "subject_source": s_pfx,
                        "subject_source_version": ROMULUS_VERSIONS.get(s_pfx, "1.0"),
                        "object_source": o_pfx,
                        "object_source_version": ROMULUS_VERSIONS.get(o_pfx, "1.0"),
                        "license": "https://w3id.org/sssom/license/unspecified",
                    }
                    if _is_url(source):
                        m["mapping_provider"] = source

                    # Comments for inconsistencies, method, or non-mappable status
                    comment_parts = []
                    if mappable.lower() == "no":
                        comment_parts.append("Mappable: No.")
                    if inconsistency != "-":
                        comment_parts.append(f"Mediation Inconsistency: {inconsistency}")
                    if method != "-":
                        comment_parts.append(f"Mediation Method: {method}")
                    if comment_parts:
                        m["comment"] = " ".join(comment_parts)

                    mappings.append(m)
                continue

        source_lower = source.lower()
        if "datacite-to-dcat-ap" in source_lower:
            # Table 4 contains the canonical DataCite to DCAT-AP property mappings
            tables_in_page = soup.find_all("table")
            table4 = tables_in_page[4] if len(tables_in_page) > 4 else None
            if table4:
                cur_elem = ""
                seen_pairs = set()
                for tr in table4.find_all("tr")[1:]:
                    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                    if not cells:
                        continue
                    first_cell = cells[0].strip()
                    if first_cell and not first_cell.startswith(("@", "*", "?")) and not ":" in first_cell and not first_cell.startswith("[["):
                        cur_elem = first_cell
                    for cell in cells:
                        tokens = re.findall(r"\b((?:dct|dcterms|dcat|foaf|vcard|adms|skos|locn):[a-z][A-Za-z0-9_]*)\b", cell)
                        for token in tokens:
                            pfx, term = token.split(":", 1)
                            norm_pfx = "dcterms" if pfx == "dct" else pfx
                            target_id = f"{norm_pfx}:{term}"
                            elem_clean = re.sub(r"[^A-Za-z0-9]", "", cur_elem)
                            pair_key = (f"datacite:{elem_clean}", target_id)
                            if elem_clean and pair_key not in seen_pairs:
                                seen_pairs.add(pair_key)
                                mappings.append({
                                    "subject_id": f"datacite:{elem_clean}",
                                    "predicate_id": "skos:exactMatch",
                                    "object_id": target_id,
                                    "mapping_justification": "semapv:ManualMappingCuration",
                                    "mapping_tool": "European Commission JRC Crosswalk",
                                    "mapping_tool_version": "2021",
                                    "author_id": "https://ec.europa.eu/jrc",
                                    "author_label": "European Commission Joint Research Centre",
                                    "license": "https://creativecommons.org/licenses/by/4.0/",
                                })
            continue

        if "prov-dc" in source_lower:
            for table in tables:
                for row in table[1:]:
                    if len(row) >= 3:
                        c1, rel, c2 = row[0].strip(), row[1].strip(), row[2].strip()
                        if ":" in c1 and ":" in c2:
                            p1 = c1.split(":")[0].lower()
                            p2 = c2.split(":")[0].lower()
                            if (p1 in ["dct", "dcterms", "dc"] and p2 == "prov") or (p1 == "prov" and p2 in ["dct", "dcterms", "dc"]):
                                pred = "skos:exactMatch"
                                if "subproperty" in rel.lower():
                                    pred = "rdfs:subPropertyOf"
                                elif "subclass" in rel.lower():
                                    pred = "rdfs:subClassOf"
                                elif "equivalent" in rel.lower():
                                    pred = "owl:equivalentClass"

                                c1_norm = c1.replace("dct:", "dcterms:").replace("dc:", "dcterms:")
                                c2_norm = c2.replace("dct:", "dcterms:").replace("dc:", "dcterms:")
                                m_row = {
                                    "subject_id": c1_norm,
                                    "predicate_id": pred,
                                    "object_id": c2_norm,
                                    "mapping_justification": "semapv:ManualMappingCuration",
                                    "mapping_tool": "W3C PROV-DC Working Group",
                                    "mapping_tool_version": "2013",
                                    "author_id": "https://www.w3.org/TR/prov-dc/",
                                    "author_label": "W3C Provenance Working Group",
                                    "license": "https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document",
                                }
                                if len(row) >= 4 and row[3].strip():
                                    m_row["comment"] = row[3].strip()
                                mappings.append(m_row)
            continue

        # DCAT-AP to Schema.org format
        # Look for rows containing CURIEs (col with ':' and another col with ':')
        for row in table[1:]:
            curie_cells = [c for c in row if ":" in c and not c.startswith("http")]
            # Match patterns like foaf:Agent and schema:Organization|schema:Person
            dcat_terms = []
            schema_terms = []
            for cell in curie_cells:
                for token in cell.split("|"):
                    token = token.strip().strip("[]()")
                    if ":" in token and not " " in token:
                        pfx = token.split(":")[0]
                        if pfx in ["dcat", "dcatap", "dcterms", "foaf", "vcard", "adms"]:
                            dcat_terms.append(token)
                        elif pfx in ["schema"]:
                            schema_terms.append(token)

            for dt in dcat_terms:
                for st in schema_terms:
                    mappings.append({
                        "subject_id": dt,
                        "predicate_id": "skos:exactMatch",
                        "object_id": st,
                        "mapping_justification": "semapv:ManualMappingCuration",
                        "mapping_tool": "European Commission JRC Crosswalk",
                        "mapping_tool_version": "2021",
                        "author_id": "https://ec.europa.eu/jrc",
                        "author_label": "European Commission Joint Research Centre",
                        "license": "https://creativecommons.org/licenses/by/4.0/",
                    })

    # If no mappings found yet, try extracting any pair of columns with entity terms
    if not mappings and tables:
        for table in tables:
            if len(table) > 1 and len(table[0]) >= 2:
                for row in table[1:]:
                    if len(row) >= 2 and row[0] and row[1]:
                        s = row[0].strip()
                        o = row[1].strip()
                        if s and o and s != o and not s.isdigit():
                            mappings.append({
                                "subject_id": s if ":" in s else f"source:{s}",
                                "predicate_id": "skos:exactMatch",
                                "object_id": o if ":" in o else f"target:{o}",
                                "mapping_justification": "semapv:ManualMappingCuration",
                                "license": "https://w3id.org/sssom/license/unspecified",
                            })

    LOGGER.info("Extracted %d mappings from webpage %s", len(mappings), source)
    res: Dict[str, Any] = {
        "curie_map": curie_map,
        "mappings": mappings,
    }
    source_lower = source.lower()
    if "datacite-to-dcat-ap" in source_lower:
        res["subject_source"] = "datacite"
        res["subject_source_version"] = "4.4"
        res["object_source"] = "dcatap"
        res["object_source_version"] = "2.1.1"
        res["mapping_set_version"] = "2021"
        res["mapping_tool"] = "European Commission JRC Crosswalk"
        res["mapping_tool_version"] = "2021"
        res["license"] = "https://creativecommons.org/licenses/by/4.0/"
    elif "prov-dc" in source_lower:
        res["subject_source"] = "dcterms"
        res["subject_source_version"] = "2020"
        res["object_source"] = "prov"
        res["object_source_version"] = "2013"
        res["mapping_set_version"] = "2013"
        res["mapping_tool"] = "W3C PROV-DC Working Group"
        res["mapping_tool_version"] = "2013"
        res["license"] = "https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document"
    elif any(m.get("subject_id", "").startswith("dcat") for m in mappings[:5]):
        res["subject_source"] = "dcat"
        res["subject_source_version"] = "2.1.1"
        res["object_source"] = "schema"
        res["object_source_version"] = "26.0"
        res["mapping_set_version"] = "2024"
        res["license"] = "https://creativecommons.org/licenses/by/4.0/"
    elif mappings and mappings[0].get("license"):
        res["license"] = mappings[0]["license"]
    else:
        res["license"] = "https://w3id.org/sssom/license/unspecified"

    return res


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract SSSOM mappings from webpage.")
    parser.add_argument("source", help="URL or path to HTML file.")
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