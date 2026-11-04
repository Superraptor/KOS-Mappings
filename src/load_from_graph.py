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
    "sio": "http://semanticscience.org/resource/SIO_",
    "ro": "http://purl.obolibrary.org/obo/RO_",
    "eli": "http://data.europa.eu/eli/ontology#",
    "gs1": "https://ref.gs1.org/voc/",
    "unece": "http://unece.org/vocab#",
    "snomedct": "http://purl.bioontology.org/ontology/SNOMEDCT/",
    "cco": "http://www.ontologyrepository.com/CommonCoreOntologies/",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
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
    elif "www.w3.org/2003/01/geo/wgs84_pos#" in uri_str:
        ident = uri_str.split("#")[-1]
        prefixes["geo"] = "http://www.w3.org/2003/01/geo/wgs84_pos#"
        return f"geo:{ident}"
    elif uri_str.startswith("http://schema.org/") or uri_str.startswith("https://schema.org/"):
        ident = uri_str.rstrip("/").split("/")[-1]
        prefixes["schema"] = "http://schema.org/"
        return f"schema:{ident}"

    # 4. Check explicit prefixes (longest prefix match first)
    best_match = None
    best_len = 0
    for pfx, ns in sorted(prefixes.items(), key=lambda item: len(item[1]), reverse=True):
        if ns and uri_str.startswith(ns) and len(ns) > best_len:
            best_match = (pfx, uri_str[len(ns):])
            best_len = len(ns)

    if best_match and best_match[1]:
        pfx_norm = best_match[0]
        if pfx_norm in ("schema1", "schema"):
            pfx_norm = "schema"
        elif pfx_norm in ("geo1", "geo"):
            pfx_norm = "geo"
        return f"{pfx_norm}:{best_match[1]}"

    # 5. Try rdflib namespace_manager.qname, BUT reject auto-generated 'ns1', 'ns2', etc.
    try:
        qname = graph.namespace_manager.qname(uri)
        if qname and ":" in qname:
            pfx_cand, local_cand = qname.split(":", 1)
            if not re.match(r"^ns\d+$", pfx_cand, re.IGNORECASE) and pfx_cand != "default":
                if pfx_cand in ("schema1", "schema"):
                    pfx_cand = "schema"
                elif pfx_cand in ("geo1", "geo"):
                    pfx_cand = "geo"
                return f"{pfx_cand}:{local_cand}"
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
            # Healing fallback for common Turtle syntax omissions (missing : or xsd: prefixes)
            healed_text = (
                f"@prefix : <{source}#> .\n"
                f"@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
                f"@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
                f"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
                f"@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
                + text
            )
            try:
                g.parse(data=healed_text, format="turtle")
                LOGGER.info("Successfully parsed graph after Turtle prefix healing (%d triples)", len(g))
                parsed = True
            except Exception:
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

        def _norm_curie(c: str) -> str:
            if not c or ":" not in c:
                return c
            p, loc = c.split(":", 1)
            p_low = p.lower()
            if p_low in ("schema1", "schema"):
                p = "schema"
            elif p_low in ("geo1", "geo"):
                p = "geo"
            return f"{p}:{loc}"

        s_curie = _norm_curie(_uri_to_curie(s, g, prefixes, default_prefix))
        o_curie = _norm_curie(_uri_to_curie(o, g, prefixes, default_prefix))

        # Skip language / ontology container typing
        if o_curie in ["owl:Ontology", "owl:Class", "rdfs:Class", "rdf:Property"] and pred_curie in ["rdf:type", "rdfs:subClassOf"]:
            continue

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

    # Check for OWL 2 annotated axioms (e.g., PROV-to-BFO alignments)
    SSOM_OBJ_LABEL = rdflib.URIRef("https://w3id.org/sssom/object_label")
    for ax, _, _ in g.triples((None, rdflib.RDF.type, rdflib.OWL.Axiom)):
        src = g.value(ax, rdflib.OWL.annotatedSource)
        prop = g.value(ax, rdflib.OWL.annotatedProperty)
        tgt = g.value(ax, rdflib.OWL.annotatedTarget)
        if not src or not prop:
            continue

        p_str = str(prop)
        pred_curie = COMMON_MAPPING_PREDICATES.get(p_str)
        if not pred_curie:
            p_lower = p_str.lower()
            if any(term in p_lower for term in [
                "subclassof", "subpropertyof", "equivalentclass", "equivalentproperty", "sameas"
            ]):
                pred_curie = _uri_to_curie(prop, g, prefixes, default_prefix)
        if not pred_curie:
            continue

        s_curie = _uri_to_curie(src, g, prefixes, default_prefix) if isinstance(src, URIRef) else None
        if not s_curie:
            continue

        o_curie = None
        o_label = None
        if isinstance(tgt, URIRef):
            o_curie = _uri_to_curie(tgt, g, prefixes, default_prefix)
            if str(tgt) in labels:
                o_label = labels[str(tgt)]

        ax_label = g.value(ax, SSOM_OBJ_LABEL)
        if ax_label:
            o_label = str(ax_label).strip()

        if o_curie:
            if s_curie == o_curie:
                continue
            s_pfx = s_curie.split(":")[0].lower() if ":" in s_curie else ""
            o_pfx = o_curie.split(":")[0].lower() if ":" in o_curie else ""
            if s_pfx and o_pfx and s_pfx == o_pfx:
                continue

            triple_key = (s_curie, pred_curie, o_curie)
            if triple_key not in seen_triples:
                seen_triples.add(triple_key)
                row = {
                    "subject_id": s_curie,
                    "predicate_id": pred_curie,
                    "object_id": o_curie,
                    "mapping_justification": "semapv:ManualMappingCuration",
                }
                if str(src) in labels:
                    row["subject_label"] = labels[str(src)]
                if o_label:
                    row["object_label"] = o_label
                mapping_rows.append(row)

    LOGGER.info("Extracted %d SSSOM mapping rows from %s", len(mapping_rows), source)

    OWL_NS = rdflib.Namespace("http://www.w3.org/2002/07/owl#")
    DCTERMS_NS = rdflib.Namespace("http://purl.org/dc/terms/")
    graph_version = None
    for _, _, o in g.triples((None, OWL_NS.versionInfo, None)):
        graph_version = str(o).strip()
        break
    if not graph_version:
        for _, _, o in g.triples((None, OWL_NS.versionIRI, None)):
            m_ver = re.search(r"v?(\d{4}[-_]\d{2}[-_]\d{2}|\d+(?:\.\d+)+)", str(o))
            if m_ver:
                graph_version = m_ver.group(1).replace("_", "-")
                break
    if not graph_version:
        for _, _, o in g.triples((None, DCTERMS_NS.hasVersion, None)):
            graph_version = str(o).strip()
            break

    # Extract license from graph triples
    graph_license = None
    for lic_pred in [
        DCTERMS_NS.license,
        rdflib.URIRef("http://purl.org/dc/elements/1.1/license"),
        rdflib.URIRef("http://schema.org/license"),
        rdflib.URIRef("https://schema.org/license"),
        rdflib.URIRef("http://usefulinc.com/ns/doap#license"),
        rdflib.URIRef("http://creativecommons.org/ns#license"),
        rdflib.URIRef("http://purl.org/dc/elements/1.1/rights"),
        DCTERMS_NS.rights,
    ]:
        for _, _, o in g.triples((None, lic_pred, None)):
            lic_val = str(o).strip()
            m_url = re.search(r"https?://[^\s\"'>)]+", lic_val)
            graph_license = m_url.group(0) if m_url else lic_val
            break
        if graph_license:
            break

    # Known repository/source license inheritance
    source_lower = source.lower()
    if not graph_license:
        if "sio-ro-bridge" in source_lower:
            graph_license = "http://creativecommons.org/licenses/by/4.0/"
        elif "schemaorg" in source_lower or "schema.org" in source_lower:
            graph_license = "https://creativecommons.org/licenses/by-sa/3.0/"
        elif "prov-bfo" in source_lower or "prov-to-bfo" in source_lower:
            graph_license = "http://creativecommons.org/publicdomain/zero/1.0/"
        elif "sumo" in source_lower:
            graph_license = "https://spdx.org/licenses/GPL-2.0-only"
        elif "dcat-prov" in source_lower:
            graph_license = "https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document"
        elif "bibo2spar" in source_lower:
            graph_license = "http://creativecommons.org/licenses/by/2.5/"

    if not graph_license:
        graph_license = "https://w3id.org/sssom/license/unspecified"

    # Enrich rows with license
    for r in mapping_rows:
        if not r.get("license"):
            s_id = r.get("subject_id", "")
            if s_id.startswith("sio:"):
                r["license"] = "http://creativecommons.org/licenses/by/4.0/"
            elif s_id.startswith("ro:") or s_id.startswith("bfo:"):
                r["license"] = "http://creativecommons.org/publicdomain/zero/1.0/"
            else:
                r["license"] = graph_license

    # Clean up prefixes dictionary
    norm_curie_map = {}
    for pfx, ns in prefixes.items():
        if re.match(r"^ns\d+$", pfx, re.IGNORECASE):
            continue
        pfx_norm = pfx
        if pfx.lower() == "schema1":
            pfx_norm = "schema"
        elif pfx.lower() == "geo1":
            pfx_norm = "geo"
        norm_curie_map[pfx_norm] = ns

    # Resolve graph origination date
    graph_date = None
    if "sumo" in source_lower:
        graph_date = "2010-09-01"
    elif "prov-bfo" in source_lower or "prov-to-bfo" in source_lower:
        graph_date = "2025-01-19"
    elif "bibo2spar" in source_lower:
        graph_date = "2018-06-21"
    elif "bibo.ttl" in source_lower or ("bibo" in source_lower and "schema" in source_lower):
        graph_date = "2011-12-01"
    elif "dcat-prov" in source_lower:
        graph_date = "2013-04-30"
    elif "sio-ro" in source_lower or "sio" in source_lower:
        graph_date = "2014-03-12"
    elif "schemaorg" in source_lower or "schema.org" in source_lower:
        graph_date = "2024-04-04"

    if graph_date:
        for r in mapping_rows:
            if not r.get("mapping_date"):
                r["mapping_date"] = graph_date

    result_dict: Dict[str, Any] = {
        "curie_map": norm_curie_map,
        "mappings": mapping_rows,
        "license": graph_license,
    }
    if graph_date:
        result_dict["mapping_date"] = graph_date
        result_dict["publication_date"] = graph_date
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