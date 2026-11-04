#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for KOS-Mappings loaders and SSSOM writing pipeline.
"""

import io
import os
import sys
import tempfile
from pathlib import Path

import pytest
import sssom.parsers

# Ensure root and src on sys.path
_TEST_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _TEST_DIR.parent
_SRC_DIR = _ROOT_DIR / "src"
for d in [str(_ROOT_DIR), str(_SRC_DIR)]:
    if d not in sys.path:
        sys.path.insert(0, d)

from src.load_from_graph import load as load_graph
from src.load_from_sssom import load as load_sssom
from src.load_from_spreadsheet import load as load_spreadsheet
from src.load_from_webpage import load as load_webpage
from src.load_from_document import load as load_document
from src.generate_sssom_metadata import generate_metadata
from src.write_sssom_file import write_sssom_file, _write_sssom_tsv, _read_sssom_tsv


def test_load_graph_sample():
    sample_ttl = _SRC_DIR / "sample.ttl"
    res = load_graph(str(sample_ttl))
    assert "curie_map" in res
    assert "mappings" in res
    assert isinstance(res["mappings"], list)


def test_load_spreadsheet_csv(tmp_path):
    csv_file = tmp_path / "test_gem.csv"
    csv_file.write_text("icd10cm,icd9cm,approximate\nA000,0010,0\nA001,0011,1\n", encoding="utf-8")
    res = load_spreadsheet(str(csv_file))
    assert len(res["mappings"]) == 2
    m1 = res["mappings"][0]
    assert m1["subject_id"] == "icd10cm:A000"
    assert m1["object_id"] == "icd9cm:0010"
    assert m1["predicate_id"] == "skos:exactMatch"
    m2 = res["mappings"][1]
    assert m2["predicate_id"] == "skos:closeMatch"


def test_load_webpage_html(tmp_path):
    html_file = tmp_path / "test_table.html"
    html_content = """
    <html><body>
    <table>
      <tr><th>Entity URI</th><th>Relation</th><th>Entity URI</th></tr>
      <tr><td>http://example.org/bfo#Thing</td><td>Equivalence</td><td>http://example.org/gfo#Item</td></tr>
    </table>
    </body></html>
    """
    html_file.write_text(html_content, encoding="utf-8")
    res = load_webpage(str(html_file))
    assert len(res["mappings"]) == 1
    m = res["mappings"][0]
    assert "Thing" in m["subject_id"]
    assert "Item" in m["object_id"]
    assert m["predicate_id"] == "owl:equivalentClass"


def test_load_document_marc(tmp_path):
    marc_file = tmp_path / "test_marc.txt"
    marc_content = (
        "=LDR  00410cz  a2200145n  4500\n"
        "=010  \\\\$ash 85110761\n"
        "=150  \\\\$aRadioisotopes in urology\n"
        "=750  \\2$aUrinary Tract$xradionuclide imaging$0(DNLM)D014551\n"
    )
    marc_file.write_text(marc_content, encoding="utf-8")
    res = load_document(str(marc_file))
    assert len(res["mappings"]) == 1
    m = res["mappings"][0]
    assert m["subject_id"] == "lcsh:sh85110761"
    assert m["object_id"] == "mesh:D014551"
    assert m["predicate_id"] == "skos:exactMatch"


def test_write_and_validate_sssom(tmp_path):
    out_file = tmp_path / "test.sssom.tsv"
    meta = {
        "mapping_set_id": "https://w3id.org/commons/mappings/test_test",
        "mapping_set_title": "Test Mappings",
        "license": "CC0-1.0",
        "mapping_date": "2026-11-02",
        "curie_map": {
            "test1": "http://example.org/test1#",
            "test2": "http://example.org/test2#",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "semapv": "https://w3id.org/semapv/vocab/",
        },
    }
    rows = [
        {
            "subject_id": "test1:A",
            "predicate_id": "skos:exactMatch",
            "object_id": "test2:B",
            "mapping_justification": "semapv:ManualMappingCuration",
        }
    ]
    _write_sssom_tsv(out_file, meta, rows)

    assert out_file.is_file()
    with open(out_file, "r", encoding="utf-8") as f:
        mdf = sssom.parsers.parse_sssom_table(f)
    assert len(mdf.df) == 1


def test_curie_map_filtering(tmp_path):
    from src.write_sssom_file import _filter_curie_map

    global_cmap = {f"unused{i}": f"http://example.org/unused{i}#" for i in range(50)}
    global_cmap["doid"] = "http://purl.obolibrary.org/obo/DOID_"
    global_cmap["mesh"] = "http://id.nlm.nih.gov/mesh/"
    global_cmap["skos"] = "http://www.w3.org/2004/02/skos/core#"
    global_cmap["semapv"] = "https://w3id.org/semapv/vocab/"

    rows = [
        {
            "subject_id": "doid:1234",
            "predicate_id": "skos:exactMatch",
            "object_id": "mesh:D001",
            "mapping_justification": "semapv:ManualMappingCuration",
            "author_id": "orcid:0000-0001-2345-6789",
        }
    ]

    filtered = _filter_curie_map(global_cmap, rows, p1="doid", p2="mesh")

    # Verify that only the prefixes used in this file are retained
    assert set(filtered.keys()) == {"doid", "mesh", "skos", "semapv", "orcid"}
    for i in range(50):
        assert f"unused{i}" not in filtered


def test_structure_and_version_metadata(tmp_path):
    from src.write_sssom_file import _resolve_structure_metadata

    group_rows = [
        {
            "subject_id": "doid:1234",
            "predicate_id": "skos:exactMatch",
            "object_id": "mesh:D001",
            "mapping_justification": "semapv:ManualMappingCuration",
            "subject_source_version": "2026-07-31",
            "object_source_version": "2026",
        }
    ]
    meta = {
        "mapping_date": "2026-11-02",
        "mapping_provider": "https://github.com/biopragmatics/biomappings",
    }

    resolved = _resolve_structure_metadata("doid", "mesh", group_rows, meta)

    assert resolved["subject_source"] == "doid"
    assert resolved["object_source"] == "mesh"
    assert resolved["subject_source_version"] == "2026-07-31"
    assert resolved["object_source_version"] == "2026"
    assert resolved["mapping_set_version"] == "2026-11-02"
    assert resolved["mapping_tool"] == "Biomappings"
    assert resolved["mapping_tool_version"] == "0.1.0"


def test_row_metadata_enrichment(tmp_path):
    from src.write_sssom_file import _enrich_row_metadata, _write_sssom_tsv

    rows = [
        {
            "subject_id": "doid:0040091",
            "predicate_id": "skos:exactMatch",
            "object_id": "mesh:D000081012",
            "subject_label": "autoimmune pancreatitis",
            "object_label": "Autoimmune Pancreatitis",
        }
    ]
    meta = {
        "mapping_set_id": "https://w3id.org/commons/mappings/doid_mesh",
        "mapping_set_title": "DOID to MESH Mappings",
        "subject_source": "doid",
        "subject_source_version": "2026-07-31",
        "object_source": "mesh",
        "object_source_version": "2026",
        "mapping_tool": "Biomappings",
        "mapping_tool_version": "0.1.0",
        "mapping_date": "2026-11-02",
        "mapping_provider": "https://example.org/test.tsv",
        "license": "CC0-1.0",
    }

    enriched = _enrich_row_metadata(rows, meta, "doid", "mesh")
    assert len(enriched) == 1
    r = enriched[0]

    # Every row contains all additional metadata
    assert r["subject_source"] == "doid"
    assert r["subject_source_version"] == "2026-07-31"
    assert r["object_source"] == "mesh"
    assert r["object_source_version"] == "2026"
    assert r["mapping_tool"] == "Biomappings"
    assert r["mapping_tool_version"] == "0.1.0"
    assert r["mapping_date"] == "2026-11-02"
    assert r["mapping_provider"] == "https://example.org/test.tsv"
    assert r["license"] == "CC0-1.0"
    assert r["mapping_justification"] == "semapv:ManualMappingCuration"


def test_romulus_metadata_extraction(tmp_path):
    from src.load_from_webpage import load

    html = """
    <table>
      <tr>
        <th></th><th>Entity URI</th><th>Relation</th><th>Entity URI</th>
        <th>Mappable</th><th>Mediation Inconsistency</th><th>Mediation Date</th>
        <th>Mediation Method</th><th>Mediation Tool</th><th>Creator</th>
      </tr>
      <tr>
        <td>1.</td>
        <td>http://www.ifomis.org/bfo/1.1#Entity</td>
        <td>Equivalence</td>
        <td>http://www.onto-med.de/ontologies/gfo.owl#Entity</td>
        <td>Yes</td>
        <td>-</td>
        <td>2012-11-21</td>
        <td>Automatic</td>
        <td>YAM++ v1.0, LogMap v2.0</td>
        <td>Zubeida Khan: zkhan@csir.co.za</td>
      </tr>
      <tr>
        <td>2.</td>
        <td>http://www.ifomis.org/bfo/1.1/snap#DependentContinuant</td>
        <td>Equivalence</td>
        <td>http://www.onto-med.de/ontologies/gfo.owl#Dependent</td>
        <td>No</td>
        <td>Inconsistency due to disjoint classes</td>
        <td>2012-11-21</td>
        <td>Manual</td>
        <td>-</td>
        <td>Zubeida Khan: zkhan@csir.co.za</td>
      </tr>
    </table>
    """
    test_file = tmp_path / "romulus_sample.html"
    test_file.write_text(html, encoding="utf-8")

    res = load(str(test_file))
    mappings = res["mappings"]
    assert len(mappings) == 2

    # Row 1: automatic equivalence
    m1 = mappings[0]
    assert m1["subject_id"] == "bfo:Entity"
    assert m1["predicate_id"] == "owl:equivalentClass"
    assert m1["object_id"] == "gfo:Entity"
    assert m1["author_id"] == "mailto:zkhan@csir.co.za"
    assert m1["creator_id"] == "mailto:zkhan@csir.co.za"
    assert m1["author_label"] == "Zubeida Khan"
    assert m1["subject_source_version"] == "1.1"
    assert m1["object_source_version"] == "1.0"
    assert "YAM++" in m1["mapping_tool"]
    assert m1["mapping_justification"] == "semapv:LexicalMatching"

    # Row 2: non-mappable with inconsistency
    m2 = mappings[1]
    assert m2["subject_id"] == "bfo:DependentContinuant"
    assert m2["predicate_id"] == "skos:closeMatch"
    assert m2["object_id"] == "gfo:Dependent"
    assert "Mappable: No." in m2["comment"]
    assert "Inconsistency due to disjoint classes" in m2["comment"]
    assert m2["mapping_tool"] == "ROMULUS Mediation Framework"


def test_lcsh_mesh_combinations_and_crossref():
    from src.load_from_document import _parse_marc_authority

    marc_text = """=LDR  01055cz  a2200193n  4500
=010  \\\\$ash 85110761
=150  \\\\$aRadioisotopes in urology
=750  \\2$aUrinary Tract$xradionuclide imaging$5IEN$0(DNLM)D014551Q000531
=LDR  01055cz  a2200193n  4500
=010  \\\\$ash 85110750
=150  \\\\$aPediatric nuclear medicine
=750  \\2$81$wb$aRadionuclide Imaging$5IEN$0(DNLM)D011877
=750  \\2$81$wb$aAdolescent$5IEN$0(DNLM)D000293
=LDR  01055cz  a2200193n  4500
=010  \\\\$ash 85082696
=150  \\\\$aCholera
=750  \\2$iBroader mapping$aCholera$0(DNLM)D002771$4BM$5IEN-M
"""
    mappings = _parse_marc_authority(marc_text)
    assert len(mappings) == 4

    # Direct 1-to-1 match -> skos:exactMatch
    m_exact = next(m for m in mappings if m["subject_id"] == "lcsh:sh85110761")
    assert m_exact["predicate_id"] == "skos:exactMatch"
    assert m_exact["object_id"] == "mesh:D014551Q000531"

    # Multi-term combination ($81$wb) -> skos:narrowMatch
    combos = [m for m in mappings if m["subject_id"] == "lcsh:sh85110750"]
    assert len(combos) == 2
    assert all(c["predicate_id"] == "skos:narrowMatch" for c in combos)

    # Broader mapping ($4BM / $iBroader) -> skos:broadMatch
    m_broad = next(m for m in mappings if m["subject_id"] == "lcsh:sh85082696")
    assert m_broad["predicate_id"] == "skos:broadMatch"


def test_sssom_archive_stream_parsing():
    from src.ingest_sssom_archive import _parse_sssom_stream
    import io

    tsv_content = b"""# mapping_set_id: https://w3id.org/commons/ols/mappings/test.sssom.tsv
# mapping_provider: https://www.ebi.ac.uk/ols4/ontologies/test
# mapping_tool: https://www.ebi.ac.uk/ols4
# mapping_date: '2026-11-03'
# curie_map:
#   SEPIO: http://purl.obolibrary.org/obo/SEPIO_
#   BFO: http://purl.obolibrary.org/obo/BFO_
subject_id\tpredicate_id\tobject_id\tmapping_justification
SEPIO:0000000\trdfs:subClassOf\tBFO:0000001\tsemapv:UnspecifiedMatching
SEPIO:0000067\trdfs:subClassOf\tSEPIO:0000066\tsemapv:UnspecifiedMatching
"""
    meta, rows = _parse_sssom_stream(io.BytesIO(tsv_content), "test.sssom.tsv")

    assert meta["mapping_provider"] == "https://www.ebi.ac.uk/ols4/ontologies/test"
    # Internal triple (SEPIO->SEPIO) must be filtered out
    assert len(rows) == 1
    r = rows[0]
    assert r["subject_id"] == "sepio:0000000"
    assert r["predicate_id"] == "rdfs:subClassOf"
    assert r["object_id"] == "bfo:0000001"
    assert r["subject_source"] == "sepio"
    assert r["object_source"] == "bfo"


def test_gem_flags_predicate_selection(tmp_path):
    from src.load_from_spreadsheet import load

    csv_text = (
        "icd10cm,icd9cm,approximate,no_map,combination,scenario,choice_list\n"
        "A000,0010,0,0,0,0,0\n"        # exactMatch (approx == 0)
        "A0101,0020,1,0,0,0,0\n"       # broadMatch (approx == 1, multiple map to 0020)
        "A0102,0020,1,0,0,0,0\n"       # broadMatch
        "A021,0031,1,0,1,1,1\n"        # narrowMatch (combination == 1)
        "A021,99591,1,0,1,1,2\n"       # narrowMatch (combination == 1)
        "B001,0540,1,0,0,0,0\n"        # closeMatch (1-to-1 approx match)
        "Z999,NoDRG,1,1,0,0,0\n"       # unmappable (no_map == 1), should be skipped
    )
    test_file = tmp_path / "test_gem_predicates.csv"
    test_file.write_text(csv_text, encoding="utf-8")

    res = load(str(test_file))
    mappings = res["mappings"]
    assert len(mappings) == 6  # Z999 skipped

    # exactMatch
    m_exact = next(m for m in mappings if m["subject_id"] == "icd10cm:A000")
    assert m_exact["predicate_id"] == "skos:exactMatch"

    # broadMatch (many ICD-10 map to 0020)
    m_broad = next(m for m in mappings if m["subject_id"] == "icd10cm:A0101")
    assert m_broad["predicate_id"] == "skos:broadMatch"

    # narrowMatch (combination)
    m_narrow = [m for m in mappings if m["subject_id"] == "icd10cm:A021"]
    assert len(m_narrow) == 2
    assert all(m["predicate_id"] == "skos:narrowMatch" for m in m_narrow)

    # closeMatch (1-to-1 approx)
    m_close = next(m for m in mappings if m["subject_id"] == "icd10cm:B001")
    assert m_close["predicate_id"] == "skos:closeMatch"


def test_ebsco_mid_extraction(tmp_path):
    from src.load_from_spreadsheet import load
    import pandas as pd

    data = {
        "Coverage Policy": ["Core", "Core", "Core"],
        "Source Type": ["Academic Journal", "Book / Monograph", "Academic Journal"],
        "ISSN / ISBN": ["1046-7041", "9781560230557", ""],
        "Publication Name": ["ABNF Journal", "Addiction & Recovery", "Internal Untitled"],
        "MID": ["GXH", "9HN", "XYZ"],
    }
    df = pd.DataFrame(data)
    test_file = tmp_path / "test_ebsco.csv"
    df.to_csv(test_file, index=False)

    res = load(str(test_file))
    mappings = res["mappings"]
    # Empty ISSN should be skipped
    assert len(mappings) == 2

    # ISSN -> EBSCO MID
    m_issn = next(m for m in mappings if m["subject_id"].startswith("issn:"))
    assert m_issn["subject_id"] == "issn:1046-7041"
    assert m_issn["object_id"] == "ebsco:GXH"
    assert m_issn["subject_label"] == "ABNF Journal"

    # ISBN -> EBSCO MID
    m_isbn = next(m for m in mappings if m["subject_id"].startswith("isbn:"))
    assert m_isbn["subject_id"] == "isbn:9781560230557"
    assert m_isbn["object_id"] == "ebsco:9HN"


def test_romulus_tool_separation_and_merge_justification():
    from src.load_from_webpage import _parse_romulus_tool
    from src.write_sssom_file import _merge_rows

    tools, versions = _parse_romulus_tool(
        "YAM++ v1.0, PROMPT v3.0, Optima v3.0, LogMap v2.0, HotMatch v1.0, Hertuda v1.0"
    )
    assert tools == "YAM++|PROMPT|Optima|LogMap|HotMatch|Hertuda"
    assert versions == "1.0|3.0|3.0|2.0|1.0|1.0"

    # Test merge: manual curation strictly takes precedence over lexical matching
    r1 = {
        "subject_id": "bfo:Entity",
        "predicate_id": "owl:equivalentClass",
        "object_id": "gfo:Entity",
        "mapping_justification": "semapv:LexicalMatching",
        "mapping_tool": "YAM++|LogMap",
        "mapping_tool_version": "1.0|2.0",
    }
    r2 = {
        "subject_id": "bfo:Entity",
        "predicate_id": "owl:equivalentClass",
        "object_id": "gfo:Entity",
        "mapping_justification": "semapv:ManualMappingCuration",
        "mapping_tool": "ROMULUS Mediation Framework",
        "mapping_tool_version": "1.0",
    }
    merged, _ = _merge_rows([r1], [r2])
    assert len(merged) == 1
    m = merged[0]
    assert m["mapping_justification"] == "semapv:ManualMappingCuration"
    assert m["mapping_tool"] == "YAM++|LogMap|ROMULUS Mediation Framework"
    assert m["mapping_tool_version"] == "1.0|2.0"


def test_license_inheritance_and_no_blind_cc0(tmp_path):
    """Ensure licenses are inherited from constituent resources and not falsely defaulted to CC0-1.0."""
    from src.write_sssom_file import _resolve_structure_metadata, _enrich_row_metadata

    # 1. Row with specific license inherits that license
    rows_mit = [
        {
            "subject_id": "test:A",
            "predicate_id": "skos:exactMatch",
            "object_id": "test:B",
            "license": "https://spdx.org/licenses/MIT",
        }
    ]
    meta_empty = {}
    resolved = _resolve_structure_metadata("test", "test", rows_mit, meta_empty)
    assert resolved["license"] == "https://spdx.org/licenses/MIT"

    # 2. Rows without license and without metadata license get unspecified, not CC0-1.0
    rows_no_lic = [
        {
            "subject_id": "test:A",
            "predicate_id": "skos:exactMatch",
            "object_id": "test:B",
        }
    ]
    resolved_unspec = _resolve_structure_metadata("test", "test", rows_no_lic, meta_empty)
    assert resolved_unspec["license"] == "https://w3id.org/sssom/license/unspecified"

    enriched = _enrich_row_metadata(rows_no_lic, meta_empty, "test", "test")
    assert enriched[0]["license"] == "https://w3id.org/sssom/license/unspecified"


def test_reverse_and_pcs_gem_loading(tmp_path):
    """Test GEM loading handles both directions and PCS codes with public domain license."""
    # Reverse CM: icd9 to icd10
    csv_rev = tmp_path / "icd9toicd10cmgem.csv"
    csv_rev.write_text("icd9cm,icd10cm,approximate,no_map,combination\n0010,A000,0,0,0\n", encoding="utf-8")
    res_rev = load_spreadsheet(str(csv_rev))
    assert res_rev["subject_source"] == "icd9cm"
    assert res_rev["object_source"] == "icd10cm"
    assert res_rev["license"] == "https://creativecommons.org/publicdomain/mark/1.0/"
    assert res_rev["mappings"][0]["subject_id"] == "icd9cm:0010"
    assert res_rev["mappings"][0]["object_id"] == "icd10cm:A000"

    # PCS GEM
    csv_pcs = tmp_path / "icd10pcstoicd9gem.csv"
    csv_pcs.write_text("icd10cm,icd9cm,approximate,no_map,combination\n0016070,0231,1,0,0\n", encoding="utf-8")
    res_pcs = load_spreadsheet(str(csv_pcs))
    assert res_pcs["subject_source"] == "icd10pcs"
    assert res_pcs["object_source"] == "icd9pcs"
    assert res_pcs["mappings"][0]["subject_id"] == "icd10pcs:0016070"
    assert res_pcs["mappings"][0]["object_id"] == "icd9pcs:0231"


def test_datacite_to_dcatap_webpage_loading(tmp_path):
    """Test extracting DataCite to DCAT-AP table mappings from HTML."""
    html_file = tmp_path / "datacite_test.html"
    html_file.write_text("""
    <html><body>
    <table><tr><th>Dummy</th></tr></table>
    <table><tr><th>Dummy</th></tr></table>
    <table><tr><th>Dummy</th></tr></table>
    <table><tr><th>Dummy</th></tr></table>
    <table>
      <tr><th>Element</th><th>Property</th><th>Range</th><th>Status</th><th>Comments</th></tr>
      <tr><td>Creator</td><td>dct:creator</td><td>foaf:Agent</td><td>testing</td><td></td></tr>
      <tr><td>Title</td><td>dct:title</td><td>rdf:PlainLiteral</td><td>testing</td><td></td></tr>
    </table>
    </body></html>
    """, encoding="utf-8")
    res = load_webpage(str(html_file))
    # Test fallback extraction or custom parsing
    assert "curie_map" in res
    assert "mappings" in res


def test_prov_dc_webpage_loading(tmp_path):
    """Test extracting Dublin Core to PROV mappings from HTML."""
    html_file = tmp_path / "prov_dc_test.html"
    html_file.write_text("""
    <html><body>
    <table>
      <tr><th>DC Term</th><th>Relation</th><th>PROV Term</th><th>Rationale</th></tr>
      <tr><td>dct:created</td><td>rdfs:subPropertyOf</td><td>prov:generatedAtTime</td><td>Time of creation</td></tr>
      <tr><td>dct:Agent</td><td>owl:equivalentClass</td><td>prov:Agent</td><td>Same concept</td></tr>
    </table>
    </body></html>
    """, encoding="utf-8")
    # Path with prov-dc in name triggers prov-dc parser
    named_file = tmp_path / "prov-dc-test.html"
    html_file.rename(named_file)
    res = load_webpage(str(named_file))
    mappings = res["mappings"]
    assert len(mappings) == 2
    assert mappings[0]["subject_id"] == "dcterms:created"
    assert mappings[0]["predicate_id"] == "rdfs:subPropertyOf"
    assert mappings[0]["object_id"] == "prov:generatedAtTime"
    assert mappings[1]["subject_id"] == "dcterms:Agent"
    assert mappings[1]["predicate_id"] == "owl:equivalentClass"
    assert mappings[1]["object_id"] == "prov:Agent"
    assert mappings[0]["license"] == "https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document"

def test_owl_axiom_and_turtle_prefix_healing(tmp_path):
    """Test healing Turtle prefix omissions and extracting OWL 2 annotated axioms with licenses."""
    ttl_file = tmp_path / "test_axioms.ttl"
    # Note: intentionally omitting @prefix : and @prefix xsd: to test healing
    ttl_content = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix bfo: <http://purl.obolibrary.org/obo/BFO_> .
@prefix dc: <http://purl.org/dc/elements/1.1/> .
@prefix sssom: <https://w3id.org/sssom/> .

<https://example.org/ont> a owl:Ontology ;
    dc:license <https://creativecommons.org/publicdomain/zero/1.0/> .

:x a rdf:Property .
"val"^^xsd:string .

[] a owl:Axiom ;
    owl:annotatedSource prov:Activity ;
    owl:annotatedProperty owl:equivalentClass ;
    owl:annotatedTarget bfo:0000015 ;
    sssom:object_label "process" .

[] a owl:Axiom ;
    owl:annotatedSource prov:Role ;
    owl:annotatedProperty rdfs:subClassOf ;
    owl:annotatedTarget bfo:0000023 ;
    sssom:object_label "role" .
"""
    ttl_file.write_text(ttl_content, encoding="utf-8")
    res = load_graph(str(ttl_file))
    mappings = res["mappings"]
    assert len(mappings) == 2
    assert res["license"] == "https://creativecommons.org/publicdomain/zero/1.0/"
    
    m0 = next(m for m in mappings if m["subject_id"] == "prov:Activity")
    assert m0["predicate_id"] == "owl:equivalentClass"
    assert m0["object_id"] == "bfo:0000015"
    assert m0["object_label"] == "process"
    assert m0["license"] == "https://creativecommons.org/publicdomain/zero/1.0/"

    m1 = next(m for m in mappings if m["subject_id"] == "prov:Role")
    assert m1["predicate_id"] == "rdfs:subClassOf"
    assert m1["object_id"] == "bfo:0000023"
    assert m1["object_label"] == "role"
    assert m1["license"] == "https://creativecommons.org/publicdomain/zero/1.0/"


def test_rda_crosswalk_parsing_legitimate_properties():
    """Ensure RDA crosswalk spreadsheet extracts legitimate property mappings, not classes-to-properties."""
    from src.load_from_document import _parse_rda_crosswalk_excel

    res = _parse_rda_crosswalk_excel("https://doi.org/10.15497/RDA00069")
    mappings = res["mappings"]
    assert len(mappings) > 30

    # Ensure metadata attributes reflect origination date and license
    assert res["mapping_date"] == "2022-03-09"
    assert res["publication_date"] == "2022-03-09"
    assert res["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert "schema" in res["curie_map"]
    assert "dcterms" in res["curie_map"]
    assert "propertyrrequired" not in res["curie_map"]
    assert "propertyrequired" not in res["curie_map"]

    # Verify that mappings are property-to-property and no bogus 'propertyrequired' or '(R)' exists
    for m in mappings:
        s = m["subject_id"]
        o = m["object_id"]
        assert "propertyrequired" not in s.lower()
        assert "propertyrequired" not in o.lower()
        assert "(" not in s and ")" not in s
        assert "(" not in o and ")" not in o
        assert m["mapping_date"] == "2022-03-09"
        assert m["license"] == "https://creativecommons.org/licenses/by/4.0/"

    # Check known property mappings
    equivs = {(m["subject_id"], m["object_id"]) for m in mappings}
    assert ("schema:description", "dcterms:description") in equivs
    assert ("schema:name", "dcterms:title") in equivs


def test_origination_dates_preservation():
    """Ensure loaders and metadata resolution preserve authentic origination dates instead of current creation date."""
    from src.write_sssom_file import _resolve_structure_metadata, _enrich_row_metadata, KNOWN_ORIGINATION_DATES

    # 1. Known historical dates check
    assert KNOWN_ORIGINATION_DATES["icd10cm_icd9cm"] == "2017-10-01"
    assert KNOWN_ORIGINATION_DATES["lcsh_mesh"] == "2018-03-27"
    assert KNOWN_ORIGINATION_DATES["rda"] == "2022-03-09"
    assert KNOWN_ORIGINATION_DATES["ebsco"] == "2024-01-01"

    # 2. Structure metadata resolution for GEM
    meta_gem = {
        "mapping_provider": "https://data.nber.org/gem/icd10cmtoicd9gem.csv",
        "mapping_tool": "CMS GEM Translation Framework",
    }
    resolved = _resolve_structure_metadata("icd10cm", "icd9cm", [], meta_gem)
    assert resolved["mapping_date"] == "2017-10-01"

    # 3. Row metadata enrichment preserves historical row dates
    rows_hist = [
        {"subject_id": "test:A", "predicate_id": "skos:exactMatch", "object_id": "test:B", "mapping_date": "2021-04-01"}
    ]
    meta_generic = {"mapping_tool": "Biomappings"}
    enriched = _enrich_row_metadata(rows_hist, meta_generic, "test", "test")
    assert enriched[0]["mapping_date"] == "2021-04-01"
