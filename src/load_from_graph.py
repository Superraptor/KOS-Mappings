#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
load_from_graph.py
------------------
Loader for RDF, OWL, and graph sources (Turtle, RDF/XML, N3, NTriples, etc.).
Extracts ontology mappings and converts them into SSSOM format.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import mimetypes
import os
import re
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import rdflib
from rdflib import BNode, Literal, URIRef
import requests

if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LOGGER = logging.getLogger(__name__)

COMMON_MAPPING_PREDICATES = {
    str(rdflib.OWL.equivalentClass): "owl:equivalentClass",
    str(rdflib.OWL.equivalentProperty): "owl:equivalentProperty",
    str(rdflib.OWL.sameAs): "owl:sameAs",
    str(rdflib.RDFS.subClassOf): "rdfs:subClassOf",
    str(rdflib.RDFS.subPropertyOf): "rdfs:subPropertyOf",
    str(rdflib.SKOS.exactMatch): "skos:exactMatch",
    str(rdflib.SKOS.closeMatch): "skos:closeMatch",
    str(rdflib.SKOS.broadMatch): "skos:broadMatch",
    str(rdflib.SKOS.narrowMatch): "skos:narrowMatch",
    str(rdflib.SKOS.relatedMatch): "skos:relatedMatch",
    "http://www.w3.org/2008/05/skos#exactMatch": "skos:exactMatch",
    "http://www.w3.org/2008/05/skos#closeMatch": "skos:closeMatch",
    "http://www.w3.org/2008/05/skos#broadMatch": "skos:broadMatch",
    "http://www.w3.org/2008/05/skos#narrowMatch": "skos:narrowMatch",
    "http://www.w3.org/2008/05/skos#relatedMatch": "skos:relatedMatch",
    "http://www.ontologyportal.org/SUMO.owl#equivalentRelation": "sumo:equivalentRelation",
    "http://www.ontologyportal.org/SUMO.owl#subsumingRelation": "sumo:subsumingRelation",
    "http://www.ontologyportal.org/SUMO.owl#subsumedRelation": "sumo:subsumedRelation",
    "https://github.com/ontologyportal/sumo#equivalentClass": "owl:equivalentClass",
    "https://github.com/ontologyportal/sumo#subClassOf": "rdfs:subClassOf",
}

DEFAULT_PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "semapv": "https://w3id.org/semapv/vocab/",
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
    "schema": "http://schema.org/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "prov": "http://www.w3.org/ns/prov#",
    "bfo": "http://purl.obolibrary.org/obo/BFO_",
    "gfo": "http://www.onto-med.de/ontologies/gfo.owl#",
    "opencyc": "http://sw.opencyc.org/concept/",
}


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _normalize_source_url(url: str) -> str:
    """Normalize raw GitHub and W3C URLs."""
    if "raw.githubusercontent.com" in url and "/refs/heads/" in url:
        url = url.replace("/refs/heads/", "/")
    if "github.com/w3c/dxwg/gh-pages/dcat/rdf/dcat-prov.ttl" in url or "w3c/dxwg" in url and "dcat-prov.ttl" in url:
        url = "https://raw.githubusercontent.com/w3c/ns/master/dcat-prov.ttl"
    return url


def _fetch_content(source: str) -> Tuple[str, str]:
    """Return raw text and inferred extension."""
    if _is_url(source):
        source = _normalize_source_url(source)
        LOGGER.info("Fetching graph content from %s", source)
        headers = {"User-Agent": "curl/7.68.0"}
        resp = requests.get(source, headers=headers, timeout=60)
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig", errors="replace")
        parsed = urllib.parse.urlparse(source)
        ext = Path(parsed.path).suffix.lower()
        return text, ext
    else:
        path = Path(source)
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
        return text, path.suffix.lower()


def _uri_to_curie(
    uri: Any,
    graph: rdflib.Graph,
    prefixes: Dict[str, str],
    default_prefix: str = "sumo",
) -> str:
    """Convert a URI to a CURIE using prefixes."""
    uri_str = str(uri).strip()

    # 1. Handle fragment identifiers or relative names (e.g., #Peru, #SocialInteraction)
    if uri_str.startswith("#"):
        ident = uri_str.lstrip("#")
        if ":" in ident:
            pfx_part, ref_part = ident.split(":", 1)
            pfx_clean = re.sub(r"[^a-zA-Z0-9_\-]", "", pfx_part).lower()
            return f"{pfx_clean}:{ref_part}"
        return f"{default_prefix}:{ident}"

    # 2. Check known raw ontology URLs (e.g. raw GitHub pointers to SUMO.owl)
    if "SUMO.owl" in uri_str or "sumo#" in uri_str.lower() or "sumo/master/" in uri_str.lower():
        ident = uri_str.split("#")[-1].split("/")[-1]
        if ":" in ident:
            pfx_part, ref_part = ident.split(":", 1)
            pfx_clean = re.sub(r"[^a-zA-Z0-9_\-]", "", pfx_part).lower()
            return f"{pfx_clean}:{ref_part}"
        return f"sumo:{ident}"

    # 3. Known domain patterns (DBpedia, YAGO, Wikipedia, WordNet, OpenCyc)
    if "dbpedia.org/resource/" in uri_str:
        ident = uri_str.split("dbpedia.org/resource/")[-1]
        prefixes["dbpedia"] = "http://dbpedia.org/resource/"
        return f"dbpedia:{ident}"
    elif "dbpedia.org/ontology/" in uri_str:
        ident = uri_str.split("dbpedia.org/ontology/")[-1]
        prefixes["dbo"] = "http://dbpedia.org/ontology/"
        return f"dbo:{ident}"
    elif "yago-knowledge.org/resource/" in uri_str:
        ident = uri_str.split("yago-knowledge.org/resource/")[-1]
        prefixes["yago"] = "http://yago-knowledge.org/resource/"
        return f"yago:{ident}"
    elif "en.wikipedia.org/wiki/" in uri_str:
        ident = uri_str.split("en.wikipedia.org/wiki/")[-1]
        prefixes["wikipedia"] = "http://en.wikipedia.org/wiki/"
        return f"wikipedia:{ident}"
    elif "WordNet.owl#" in uri_str or "/wn#" in uri_str:
        ident = uri_str.split("#")[-1]
        prefixes["wn"] = "http://www.ontologyportal.org/WordNet.owl#"
        return f"wn:{ident}"
    elif "opencyc.org/concept/" in uri_str:
        ident = uri_str.split("opencyc.org/concept/")[-1]
        prefixes["opencyc"] = "http://sw.opencyc.org/concept/"
        return f"opencyc:{ident}"

    # 4. Check explicit prefixes (longest prefix match first)
    best_match = None
    best_len = 0
    for pfx, ns in sorted(prefixes.items(), key=lambda item: len(item[1]), reverse=True):
        if ns and uri_str.startswith(ns) and len(ns) > best_len:
            best_match = (pfx, uri_str[len(ns):])
            best_len = len(ns)

    if best_match and best_match[1]:
        return f"{best_match[0]}:{best_match[1]}"

    # 5. Try rdflib namespace_manager.qname, BUT reject auto-generated 'ns1', 'ns2', etc.
    try:
        qname = graph.namespace_manager.qname(uri)
        if qname and ":" in qname:
            pfx_cand, _ = qname.split(":", 1)
            if not re.match(r"^ns\d+$", pfx_cand, re.IGNORECASE) and pfx_cand != "default":
                return qname
    except Exception:
        pass

    # Fallback to split_uri
    try:
        ns, ident = rdflib.namespace.split_uri(uri_str)
        slug = re.sub(r"[^a-zA-Z0-9]", "", Path(urllib.parse.urlparse(ns).path).name or "")
        if slug and not re.match(r"^ns\d*$", slug, re.IGNORECASE):
            if slug not in prefixes:
                prefixes[slug] = ns
            return f"{slug}:{ident}"
    except Exception:
        pass

    if not uri_str.startswith(("http://", "https://")):
        if ":" in uri_str:
            return uri_str
        return f"{default_prefix}:{uri_str}"

    return uri_str


def load(source: str, **kwargs: Any) -> Dict[str, Any]:
    """
    Load an RDF/OWL graph from source (URL or filepath) and extract SSSOM mappings.
    Returns:
        {
            "curie_map": {...},
            "mappings": [{"subject_id": ..., "predicate_id": ..., "object_id": ..., "mapping_justification": ...}, ...]
        }
    """
    text, ext = _fetch_content(source)
    g = rdflib.Graph()

    formats_to_try = []
    if ext in [".ttl"]:
        formats_to_try = ["turtle", "n3", "xml"]
    elif ext in [".owl", ".rdf", ".xml"]:
        formats_to_try = ["xml", "turtle"]
    elif ext in [".nt"]:
        formats_to_try = ["nt", "turtle"]
    elif ext in [".jsonld"]:
        formats_to_try = ["json-ld", "turtle"]
    else:
        formats_to_try = ["turtle", "xml", "n3", "nt"]

    parsed = False
    for fmt in formats_to_try:
        try:
            g.parse(data=text, format=fmt)
            LOGGER.info("Successfully parsed graph using format %s (%d triples)", fmt, len(g))
            parsed = True
            break
        except Exception as exc:
            LOGGER.debug("Format %s failed: %s", fmt, exc)

    if not parsed:
        try:
            g.parse(data=text)
            parsed = True
        except Exception as exc:
            raise RuntimeError(f"Could not parse RDF graph from {source}: {exc}") from exc

    source_lower = source.lower()
    default_prefix = "sumo" if "sumo" in source_lower else "source"
    if "dcat" in source_lower:
        default_prefix = "dcat"
    elif "bibo" in source_lower:
        default_prefix = "bibo"
    elif "bfo" in source_lower:
        default_prefix = "bfo"
    elif "gfo" in source_lower:
        default_prefix = "gfo"

    # Harvest namespaces
    prefixes = dict(DEFAULT_PREFIXES)
    for pfx, ns in g.namespace_manager.namespaces():
        pfx_str = str(pfx)
        if pfx_str and not pfx_str.startswith("_") and not re.match(r"^ns\d+$", pfx_str, re.IGNORECASE):
            prefixes[pfx_str] = str(ns)
        elif pfx_str == "" and ("sumo" in str(ns).lower() or "sumo" in source_lower):
            prefixes["sumo"] = str(ns)

    # Standardize sumo prefix if needed
    for k, v in list(prefixes.items()):
        if "sumo" in k.lower() or "sumo" in str(v).lower():
            prefixes["sumo"] = str(v)

    # Collect labels
    labels = {}
    for s, p, o in g.triples((None, rdflib.RDFS.label, None)):
        if isinstance(o, (Literal, str)):
            labels[str(s)] = str(o).strip()
    for s, p, o in g.triples((None, rdflib.SKOS.prefLabel, None)):
        if isinstance(o, (Literal, str)):
            labels[str(s)] = str(o).strip()

    mapping_rows: List[Dict[str, Any]] = []
    seen_triples = set()

    for s, p, o in g:
        # We only consider triples where subject and object are URIs
        if not isinstance(s, URIRef) or not isinstance(o, URIRef):
            continue

        s_str = str(s)
        p_str = str(p)
        o_str = str(o)

        # Ignore structural / metadata / annotation predicates
        p_lower = p_str.lower()
        if any(term in p_lower for term in [
            "rdf-syntax-ns#type", "/type", "isdefinedby", "comment", "label",
            "seealso", "versioninfo", "axiom", "domain", "range"
        ]):
            continue

        is_mapping = False
        pred_curie = COMMON_MAPPING_PREDICATES.get(p_str)

        if pred_curie:
            is_mapping = True
        else:
            # Check if p is an alignment predicate
            if any(term in p_lower for term in [
                "equivalentclass", "equivalentproperty", "equivalentrelation",
                "sameas", "exactmatch", "closematch", "broadmatch", "narrowmatch",
                "relatedmatch", "subsumingrelation", "subsumedrelation",
                "align", "mapping", "hasdbxref", "subclassof", "subpropertyof"
            ]):
                is_mapping = True
                pred_curie = _uri_to_curie(p, g, prefixes, default_prefix)

        if not is_mapping:
            continue

        s_curie = _uri_to_curie(s, g, prefixes, default_prefix)
        o_curie = _uri_to_curie(o, g, prefixes, default_prefix)

        # Skip self-mappings
        if s_curie == o_curie:
            continue

        # Skip internal taxonomy/hierarchy triples within the same ontology (e.g. sumo:A subClassOf sumo:B)
        s_pfx = s_curie.split(":")[0].lower() if ":" in s_curie else ""
        o_pfx = o_curie.split(":")[0].lower() if ":" in o_curie else ""
        if s_pfx and o_pfx and s_pfx == o_pfx:
            continue

        triple_key = (s_curie, pred_curie, o_curie)
        if triple_key in seen_triples:
            continue
        seen_triples.add(triple_key)

        row = {
            "subject_id": s_curie,
            "predicate_id": pred_curie,
            "object_id": o_curie,
            "mapping_justification": "semapv:ManualMappingCuration",
        }
        if s_str in labels:
            row["subject_label"] = labels[s_str]
        if o_str in labels:
            row["object_label"] = labels[o_str]

        mapping_rows.append(row)

    LOGGER.info("Extracted %d SSSOM mapping rows from %s", len(mapping_rows), source)

    OWL_NS = rdflib.Namespace("http://www.w3.org/2002/07/owl#")
    DCTERMS_NS = rdflib.Namespace("http://purl.org/dc/terms/")
    graph_version = None
    for _, _, o in g.triples((None, OWL_NS.versionInfo, None)):
        graph_version = str(o).strip()
        break
    if not graph_version:
        for _, _, o in g.triples((None, DCTERMS_NS.hasVersion, None)):
            graph_version = str(o).strip()
            break

    result_dict: Dict[str, Any] = {
        "curie_map": prefixes,
        "mappings": mapping_rows,
    }
    if graph_version:
        result_dict["mapping_set_version"] = graph_version
        result_dict["subject_source_version"] = graph_version

    return result_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract SSSOM mappings from RDF/OWL graph.")
    parser.add_argument("source", help="Path or URL to RDF/OWL file.")
    parser.add_argument("-o", "--output", help="Output JSON file (default: stdout).")
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