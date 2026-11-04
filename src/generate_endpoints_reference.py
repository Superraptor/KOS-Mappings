#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_endpoints_reference.py
-------------------------------
Generates comprehensive endpoint reference files:
- endpoints.tsv (tabular data with prefix, long-form name, category, URI prefix, authority)
- endpoints.txt (clean human-readable reference, e.g. "mesh: Medical Subject Headings")
- www/data/endpoints.json (JSON structure for web search & frontend)
"""

import json
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SRC_DIR.parent

WELL_KNOWN_ENDPOINTS = {
    # Core W3C & Semantics
    "rdf": ("Resource Description Framework", "W3C Standards", "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "W3C", "Foundation data model for graph knowledge representation."),
    "rdfs": ("RDF Schema", "W3C Standards", "http://www.w3.org/2000/01/rdf-schema#", "W3C", "Data modeling vocabulary for RDF data structures and hierarchies."),
    "owl": ("Web Ontology Language", "W3C Standards", "http://www.w3.org/2002/07/owl#", "W3C", "Formal description logic ontology language for semantic web."),
    "skos": ("Simple Knowledge Organization System", "W3C Standards", "http://www.w3.org/2004/02/skos/core#", "W3C", "Standard representation for thesauri, classification schemes, and subject headings."),
    "semapv": ("Semantic Mapping Vocabulary", "Mapping Standards", "https://w3id.org/semapv/vocab/", "OBO Foundry", "Vocabulary defining justification types and mediation methods for mappings."),
    "sssom": ("Simple Standard for Sharing Ontological Mappings", "Mapping Standards", "https://w3id.org/sssom/", "Mapping Commons", "Standard specification for tabular representation of ontology crosswalks."),
    "dcterms": ("Dublin Core Metadata Initiative Terms", "Metadata Standards", "http://purl.org/dc/terms/", "DCMI", "Core property terms for resource descriptions and provenance."),
    "dc": ("Dublin Core Elements", "Metadata Standards", "http://purl.org/dc/elements/1.1/", "DCMI", "Classical Dublin Core 15 element set."),
    "prov": ("W3C PROV Ontology", "Provenance", "http://www.w3.org/ns/prov#", "W3C", "Conceptual data model that forms a basis for provenance interchange."),
    "dcat": ("Data Catalog Vocabulary", "Metadata Standards", "http://www.w3.org/ns/dcat#", "W3C", "RDF vocabulary designed to facilitate interoperability between data catalogs."),
    "dcatap": ("DCAT Application Profile for Data Portals in Europe", "Metadata Standards", "http://data.europa.eu/r5r/", "European Commission", "DCAT profile for sharing public sector datasets across European data portals."),
    "schema": ("Schema.org Vocabulary", "Web Schemas", "http://schema.org/", "Schema.org Consortium", "Collaborative schema for structured data on the Internet."),
    "foaf": ("Friend of a Friend", "Web Schemas", "http://xmlns.com/foaf/0.1/", "FOAF Project", "Linking people and information using the Web."),
    "vcard": ("vCard in RDF", "Metadata Standards", "http://www.w3.org/2006/vcard/ns#", "W3C", "Ontology for electronic business card profiles and organizations."),
    "adms": ("Asset Description Metadata Schema", "Metadata Standards", "http://www.w3.org/ns/adms#", "European Commission", "Vocabulary to describe semantic interoperability assets."),

    # Identifiers & Provenance
    "orcid": ("Open Researcher and Contributor ID", "Identifiers", "https://orcid.org/", "ORCID Inc.", "Unique persistent identifier for researchers and academic contributors."),
    "wikidata": ("Wikidata Knowledge Graph", "General Knowledge", "http://www.wikidata.org/entity/", "Wikimedia Foundation", "Free, collaborative, multilingual, secondary knowledge base."),
    "doi": ("Digital Object Identifier", "Identifiers", "https://doi.org/", "International DOI Foundation", "Persistent identifier system for digital documents, datasets, and articles."),
    "pmid": ("PubMed Unique Identifier", "Identifiers", "https://pubmed.ncbi.nlm.nih.gov/", "National Library of Medicine", "Unique identifier for biomedical and life sciences literature."),
    "isbn": ("International Standard Book Number", "Bibliographic Standards", "urn:isbn:", "International ISBN Agency", "Unique commercial book identifier."),
    "issn": ("International Standard Serial Number", "Bibliographic Standards", "urn:issn:", "ISSN International Centre", "Unique eight-digit serial publication identifier."),

    # Biomedical Clinical & Laboratory Terminologies (Athena / OMOP / NLM)
    "mesh": ("Medical Subject Headings", "Health & Biomedicine", "http://id.nlm.nih.gov/mesh/", "National Library of Medicine (NLM)", "Controlled vocabulary thesaurus used for indexing PubMed/MEDLINE."),
    "snomedct": ("Systematized Nomenclature of Medicine - Clinical Terms", "Health & Biomedicine", "http://snomed.info/id/", "SNOMED International", "Comprehensive, clinically validated healthcare terminology."),
    "sctid": ("SNOMED CT Concept Identifier", "Health & Biomedicine", "http://snomed.info/id/", "SNOMED International", "Concept identifier namespace for SNOMED CT clinical terms."),
    "loinc": ("Logical Observation Identifiers Names and Codes", "Health & Biomedicine", "https://loinc.org/", "Regenstrief Institute", "Universal standard for identifying laboratory and clinical observations."),
    "ucum": ("Unified Code for Units of Measure", "Measurement Standards", "http://unitsofmeasure.org/", "Regenstrief Institute", "Standardized syntax and units of measure representation in healthcare."),
    "omop": ("OMOP Standardized Vocabulary", "Health & Biomedicine", "https://athena.ohdsi.org/search-terms/terms/", "OHDSI", "Observational Medical Outcomes Partnership Common Data Model terminology."),
    "omopext": ("OMOP Extension", "Health & Biomedicine", "https://athena.ohdsi.org/search-terms/terms/", "OHDSI", "Clinical terminology extensions curated by the OHDSI vocabulary team."),
    "rxnorm": ("RxNorm Standardized Clinical Drugs", "Pharmacology", "https://identifiers.org/rxnorm:", "National Library of Medicine (NLM)", "Standardized nomenclature for clinical drugs, ingredients, and dosages."),
    "rxnormext": ("RxNorm Extension", "Pharmacology", "https://athena.ohdsi.org/search-terms/terms/", "OHDSI", "International drug extensions adhering to RxNorm model."),
    "cpt": ("Current Procedural Terminology", "Health & Biomedicine", "https://identifiers.org/cpt:", "American Medical Association (AMA)", "Medical code set used to report medical, surgical, and diagnostic procedures."),
    "hcpcs": ("Healthcare Common Procedure Coding System", "Health & Biomedicine", "https://identifiers.org/hcpcs:", "Centers for Medicare & Medicaid Services (CMS)", "Standardized coding system for healthcare services, procedures, and equipment."),
    "atc": ("Anatomical Therapeutic Chemical Classification", "Pharmacology", "https://identifiers.org/atc:", "World Health Organization (WHO)", "Classification system dividing active substances into anatomical and therapeutic groups."),
    "ndc": ("National Drug Code", "Pharmacology", "https://identifiers.org/ndc:", "U.S. Food and Drug Administration (FDA)", "Universal product identifier for human drugs in the United States."),
    "meddra": ("Medical Dictionary for Regulatory Activities", "Pharmacology", "https://identifiers.org/meddra:", "ICH", "Clinically validated medical terminology used for regulatory data sharing."),
    "icd10": ("International Classification of Diseases, 10th Revision", "Health Classifications", "https://icd.who.int/browse10/2019/en#/", "World Health Organization (WHO)", "Global epidemiological and health diagnostic classification standard."),
    "icd10cm": ("ICD-10 Clinical Modification", "Health Classifications", "https://identifiers.org/icd10cm:", "CDC / NCHS", "Clinical modification of ICD-10 for diagnostic coding in US healthcare."),
    "icd10pcs": ("ICD-10 Procedure Coding System", "Health Classifications", "https://identifiers.org/icd10pcs:", "CMS", "Procedure coding system used in US inpatient hospital settings."),
    "icd9cm": ("ICD-9 Clinical Modification", "Health Classifications", "https://identifiers.org/icd9cm:", "CDC / CMS", "Predecessor diagnostic and procedure classification in US healthcare."),
    "icd9pcs": ("ICD-9 Procedure Coding System", "Health Classifications", "https://identifiers.org/icd9pcs:", "CMS", "Predecessor procedure coding system in US healthcare."),
    "icd11": ("International Classification of Diseases, 11th Revision", "Health Classifications", "http://id.who.int/icd/entity/", "World Health Organization (WHO)", "Modernized digital diagnostic taxonomy with post-coordination support."),
    "icd11foundation": ("ICD-11 Foundation Component", "Health Classifications", "http://id.who.int/icd/release/11/mms/", "World Health Organization (WHO)", "Multidimensional underlying knowledge base of ICD-11 entities."),

    # OBO Biological & Disease Ontologies
    "doid": ("Human Disease Ontology", "OBO Ontologies", "http://purl.obolibrary.org/obo/DOID_", "University of Maryland / OBO", "Standardized ontological representation of human disease entities."),
    "mondo": ("Mondo Disease Ontology", "OBO Ontologies", "http://purl.obolibrary.org/obo/MONDO_", "Monarch Initiative / OBO", "Harmonized ontology integrating global disease classifications into a single graph."),
    "hp": ("Human Phenotype Ontology", "OBO Ontologies", "http://purl.obolibrary.org/obo/HP_", "Monarch Initiative / OBO", "Standardized vocabulary of phenotypic abnormalities encountered in human disease."),
    "chebi": ("Chemical Entities of Biological Interest", "OBO Ontologies", "http://purl.obolibrary.org/obo/CHEBI_", "EMBL-EBI", "Dictionary of molecular entities focused on small chemical compounds."),
    "cl": ("Cell Ontology", "OBO Ontologies", "http://purl.obolibrary.org/obo/CL_", "OBO Foundry", "Structured representation of in vivo cell types in humans and model organisms."),
    "go": ("Gene Ontology", "OBO Ontologies", "http://purl.obolibrary.org/obo/GO_", "Gene Ontology Consortium", "Framework for the model of biology, detailing molecular functions and processes."),
    "uberon": ("Uber-anatomy Ontology", "OBO Ontologies", "http://purl.obolibrary.org/obo/UBERON_", "OBO Foundry", "Integrated cross-species anatomical ontology representing animal structures."),
    "ncbitaxon": ("NCBI Organismal Taxonomy", "OBO Ontologies", "http://purl.obolibrary.org/obo/NCBITaxon_", "NCBI", "Standard biological classification of all organisms represented in GenBank."),
    "taxrank": ("Taxonomic Rank Ontology", "OBO Ontologies", "http://purl.obolibrary.org/obo/TAXRANK_", "OBO Foundry", "Ontology defining ranks of biological taxa (kingdom, phylum, species, etc.)."),
    "pr": ("Protein Ontology", "OBO Ontologies", "http://purl.obolibrary.org/obo/PR_", "OBO Foundry", "Formal representation of evolutionary protein entities, classes, and complexes."),
    "so": ("Sequence Ontology", "OBO Ontologies", "http://purl.obolibrary.org/obo/SO_", "Sequence Ontology Consortium", "Structured computer-readable vocabulary for genomic sequence features."),
    "symp": ("Symptom Ontology", "OBO Ontologies", "http://purl.obolibrary.org/obo/SYMP_", "OBO Foundry", "Controlled vocabulary defining symptoms and signs of human pathology."),
    "ncit": ("NCI Thesaurus", "OBO Ontologies", "http://purl.obolibrary.org/obo/NCIT_", "National Cancer Institute (NCI)", "Comprehensive biomedical vocabulary focused on cancer research and therapeutics."),
    "umls": ("Unified Medical Language System", "Health & Biomedicine", "https://identifiers.org/umls:", "National Library of Medicine (NLM)", "Metathesaurus interconnecting diverse health classifications and terminology."),
    "medgen": ("MedGen Clinical Genetics Database", "Health & Biomedicine", "https://identifiers.org/medgen:", "NCBI", "Portal to information about medical genetics and genetic disorders."),
    "omim": ("Online Mendelian Inheritance in Man", "Genetics & Rare Diseases", "https://omim.org/entry/", "Johns Hopkins University", "Catalog of human genes and genetic phenotypes."),
    "orphanet": ("Orphanet Rare Disease Nomenclature", "Genetics & Rare Diseases", "https://identifiers.org/orphanet:", "INSERM / Orphanet", "Reference nomenclature and classification for rare diseases."),
    "drugbank": ("DrugBank Knowledgebase", "Pharmacology", "https://go.drugbank.com/drugs/", "DrugBank / OMx", "Comprehensive bio-informatic and chemo-informatic drug knowledge resource."),
    "reactome": ("Reactome Pathway Database", "Pathways & Systems Biology", "https://reactome.org/content/detail/", "Reactome Consortium", "Open-source curated database of biological pathways and reactions."),
    "wikipathways": ("WikiPathways Biological Pathway Repository", "Pathways & Systems Biology", "https://www.wikipathways.org/pathways/", "WikiPathways", "Open, collaborative platform dedicated to the curation of biological pathways."),
    "keggpathway": ("KEGG Pathway Database", "Pathways & Systems Biology", "https://www.kegg.jp/entry/", "Kanehisa Laboratories", "Collection of manually drawn pathway maps representing molecular interactions."),
    "uniprot": ("Universal Protein Resource", "Proteomics", "https://www.uniprot.org/uniprotkb/", "UniProt Consortium", "Hub for protein sequence and functional information."),
    "fma": ("Foundational Model of Anatomy", "Anatomy", "http://purl.obolibrary.org/obo/FMA_", "University of Washington", "Reference ontology for biomedical informatics in domain of human anatomy."),
    "ma": ("Mouse Adult Anatomy Ontology", "Anatomy", "http://purl.obolibrary.org/obo/MA_", "The Jackson Laboratory", "Structured vocabulary of adult mouse anatomy."),
    "emapa": ("Edinburgh Mouse Atlas Project Anatomy", "Anatomy", "http://purl.obolibrary.org/obo/EMAPA_", "EMAP / Jackson Lab", "Anatomical ontology covering developmental stages of embryonic mouse."),
    "bto": ("BRENDA Tissue Ontology", "Anatomy & Biochemistry", "http://purl.obolibrary.org/obo/BTO_", "BRENDA", "Comprehensive encyclopedia of tissues and cell types for enzyme information."),
    "caro": ("Common Anatomy Reference Ontology", "Upper Ontologies", "http://purl.obolibrary.org/obo/CARO_", "OBO Foundry", "Upper-level anatomy ontology to standardize biological structures."),

    # Upper & Foundational Ontologies
    "bfo": ("Basic Formal Ontology", "Upper Ontologies", "http://purl.obolibrary.org/obo/BFO_", "OBO Foundry / ISO/IEC 21838-2", "Top-level formal ontology designed to support domain-level ontologies."),
    "gfo": ("General Formal Ontology", "Upper Ontologies", "http://www.onto-med.de/ontologies/gfo.owl#", "Onto-Med Leipzig", "Top-level ontology integrating objects, processes, facts, and universals."),
    "dolce": ("Descriptive Ontology for Linguistic and Cognitive Engineering", "Upper Ontologies", "http://www.loa-cnr.it/ontologies/DOLCE-Lite.owl#", "ISTC-CNR", "Foundational ontology based on cognitive categories and natural language."),
    "sumo": ("Suggested Upper Merged Ontology", "Upper Ontologies", "http://www.ontologyportal.org/SUMO.owl#", "IEEE Working Group / Pease", "Formal upper ontology mapped to WordNet and English vocabulary."),
    "ro": ("OBO Relation Ontology", "Upper Ontologies", "http://purl.obolibrary.org/obo/RO_", "OBO Foundry", "Standardized ontological relations between biomedical entities."),
    "sio": ("Semanticscience Integrated Ontology", "Upper Ontologies", "http://semanticscience.org/resource/SIO_", "Dumontier Lab", "Upper-level ontology for the biomedical and health sciences."),
    "temporalrelations": ("DOLCE Temporal Relations Ontology", "Upper Ontologies", "http://www.loa-cnr.it/ontologies/TemporalRelations.owl#", "ISTC-CNR", "Formal temporal relations module for DOLCE-Lite."),
    "spatialrelations": ("DOLCE Spatial Relations Ontology", "Upper Ontologies", "http://www.loa-cnr.it/ontologies/SpatialRelations.owl#", "ISTC-CNR", "Formal spatial relations module for DOLCE-Lite."),
    "functionalparticipation": ("DOLCE Functional Participation Ontology", "Upper Ontologies", "http://www.loa-cnr.it/ontologies/FunctionalParticipation.owl#", "ISTC-CNR", "Formal participation axioms for DOLCE-Lite."),

    # Upper & Knowledge Graphs
    "dbo": ("DBpedia Ontology", "Knowledge Graphs", "http://dbpedia.org/ontology/", "DBpedia Community", "Cross-domain ontology generated from Wikipedia infoboxes."),
    "dbpedia": ("DBpedia Resource Namespace", "Knowledge Graphs", "http://dbpedia.org/resource/", "DBpedia Community", "Linked open data entity namespace extracted from Wikipedia articles."),
    "yago": ("YAGO Knowledge Base", "Knowledge Graphs", "http://yago-knowledge.org/resource/", "Max Planck Institute / Telecom Paris", "High-coverage knowledge base derived from Wikipedia, WordNet, and GeoNames."),
    "wikipedia": ("Wikipedia Article Namespace", "General Knowledge", "http://en.wikipedia.org/wiki/", "Wikimedia Foundation", "Free encyclopedia web article identifier namespace."),
    "wn": ("WordNet 3.0 Synsets", "Linguistics & Lexicons", "http://www.ontologyportal.org/WordNet.owl#", "Princeton University / SUMO", "Lexical database of semantic relations between words and synsets."),
    "wordnet": ("Princeton WordNet Lexicon", "Linguistics & Lexicons", "http://www.ontologyportal.org/WordNet.owl#", "Princeton University", "Large lexical database of English nouns, verbs, adjectives, and adverbs."),

    # Library, Authority, and Bibliographic Schemes
    "lcsh": ("Library of Congress Subject Headings", "Library & Authority", "http://id.loc.gov/authorities/subjects/", "Library of Congress", "Thesaurus of subject headings used by bibliographic libraries worldwide."),
    "gnd": ("Gemeinsame Normdatei (Integrated Authority File)", "Library & Authority", "https://d-nb.info/gnd/", "German National Library (DNB)", "German authority file for persons, corporate bodies, conferences, and subjects."),
    "viaf": ("Virtual International Authority File", "Library & Authority", "http://viaf.org/viaf/", "OCLC", "Joint project linking global national authority files into a single service."),
    "fast": ("Faceted Application of Subject Terminology", "Library & Authority", "http://id.worldcat.org/fast/", "OCLC", "Faceted Dublin Core-compatible vocabulary based on LCSH."),
    "ebsco": ("EBSCO Subject & Coverage Vocabulary", "Bibliographic Standards", "https://www.ebsco.com/terms/", "EBSCO Information Services", "Controlled indexing terms for academic journals and databases."),
    "bibo": ("Bibliographic Ontology", "Bibliographic Standards", "http://purl.org/ontology/bibo/", "DCMI / Zepheira", "Ontology for representing citations, bibliographic references, and documents."),
    "fabio": ("FRBR-aligned Bibliographic Ontology", "Bibliographic Standards", "http://purl.org/spar/fabio/", "SPAR Ontologies", "Ontology for recording publishing assets and scholarly literature."),
    "cito": ("Citation Typing Ontology", "Bibliographic Standards", "http://purl.org/spar/cito/", "SPAR Ontologies", "Ontology enabling formal characterization of citation intents and links."),
    "rda": ("Resource Description and Access Elements", "Bibliographic Standards", "http://rdaregistry.info/Elements/", "RDA Steering Committee", "Standard for cataloging and descriptive metadata in cultural heritage institutions."),

    # Geographic & Demographic Systems
    "osm": ("OpenStreetMap Tagging & Features", "Geographic Standards", "https://www.openstreetmap.org/", "OpenStreetMap Foundation", "Collaborative project to create a free editable geographic database of the world."),
    "uscensus": ("U.S. Census Bureau Classifications", "Demographic Standards", "https://www.census.gov/", "U.S. Census Bureau", "Federal statistical geographic entities, tracts, blocks, and demographic codes."),
    "gaz": ("Gazetteer of Place Names", "Geographic Standards", "http://purl.obolibrary.org/obo/GAZ_", "OBO Foundry", "Ontology of geographical places, geopolitical entities, and physical features."),
    "sopt": ("Source of Payment Typology", "Healthcare Administration", "https://athena.ohdsi.org/search-terms/terms/", "PHDSC", "National standard for categorizing healthcare payment sources and insurance."),
}


def build_endpoint_registry():
    """Compiles complete endpoint metadata and writes endpoints.tsv, endpoints.txt, and endpoints.json."""
    commons_dir = _ROOT_DIR / "commons"
    active_prefixes = set()
    if commons_dir.exists():
        for f in commons_dir.glob("*/*/*.sssom.tsv*"):
            parts = f.stem.split(".")[0].split("_")
            if len(parts) >= 2:
                active_prefixes.add(parts[0])
                active_prefixes.add(parts[1])

    all_keys = sorted(set(list(WELL_KNOWN_ENDPOINTS.keys()) + list(active_prefixes)))

    records = []
    txt_lines = [
        "# KOS-Mappings: Ontology & Knowledge Organization System Endpoint Dictionary",
        "# Describes the canonical long-form name, authority, and category for all entity prefixes.",
        "# Format: <prefix>: <Full Name> (<Authority/Standard>) - <Description>",
        "",
    ]
    tsv_lines = [
        "prefix\tname\tcategory\turi_prefix\tauthority\tdescription"
    ]

    for k in all_keys:
        if k in WELL_KNOWN_ENDPOINTS:
            name, cat, uri, auth, desc = WELL_KNOWN_ENDPOINTS[k]
        else:
            name = k.upper()
            cat = "Domain Vocabulary"
            uri = f"https://identifiers.org/{k}:"
            auth = "External Repository / Mapping Commons"
            desc = f"Domain ontology / vocabulary mapping endpoint '{k}'."

        records.append({
            "prefix": k,
            "name": name,
            "category": cat,
            "uri_prefix": uri,
            "authority": auth,
            "description": desc,
            "in_commons": k in active_prefixes,
        })

        txt_lines.append(f"{k}: {name} ({auth}) - {desc}")
        tsv_lines.append(f"{k}\t{name}\t{cat}\t{uri}\t{auth}\t{desc}")

    # Write endpoints.tsv
    tsv_path = _ROOT_DIR / "endpoints.tsv"
    tsv_path.write_text("\n".join(tsv_lines) + "\n", encoding="utf-8")

    # Write endpoints.txt
    txt_path = _ROOT_DIR / "endpoints.txt"
    txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")

    # Write www/data/endpoints.json
    www_data_dir = _ROOT_DIR / "www" / "data"
    www_data_dir.mkdir(parents=True, exist_ok=True)
    json_path = www_data_dir / "endpoints.json"
    json_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    print(f"Generated endpoints reference files with {len(records)} entries:")
    print(f"  {tsv_path}")
    print(f"  {txt_path}")
    print(f"  {json_path}")
    return records


if __name__ == "__main__":
    build_endpoint_registry()
