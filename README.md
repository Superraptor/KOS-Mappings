# KOS-Mappings

[![SSSOM Standard](https://img.shields.io/badge/SSSOM-v1.0-blue.svg)](https://mapping-commons.github.io/sssom/)
[![Mapping Commons](https://img.shields.io/badge/Registry-Mapping_Commons-green.svg)](https://mapping-commons.github.io/)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: CC0-1.0](https://img.shields.io/badge/License-CC0_1.0-lightgrey.svg)](https://creativecommons.org/publicdomain/zero/1.0/)
[![Tests](https://img.shields.io/badge/tests-23%2F23%20passing-brightgreen.svg)](test/test_loaders.py)

**KOS-Mappings** is an automated extraction, parsing, and harmonization toolkit for Knowledge Organization Systems (KOS), ontologies, thesauri, vocabulary crosswalks, and alignment tables. It converts diverse source formats into validated, high-quality [Simple Standard for Sharing Ontological Mappings (SSSOM)](https://mapping-commons.github.io/sssom/) TSV files structured for publication in the [Mapping Commons Registry](https://mapping-commons.github.io/).

---

## Table of Contents

- [Overview](#overview)
- [Mapping Commons Registry Integration](#mapping-commons-registry-integration)
- [Repository Size Limits & SSSOM Compression (`.sssom.tsv.gz`)](#repository-size-limits--sssom-compression-sssometz)
- [Vocabulary Endpoint Dictionary](#vocabulary-endpoint-dictionary)
- [Web Explorer & Semantic Pathfinder (`./www`)](#web-explorer--semantic-pathfinder)
- [Repository Structure](#repository-structure)
- [Supported Formats & Loaders](#supported-formats--loaders)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
  - [Ingesting OHDSI Athena (OMOP CDM) Vocabularies](#ingesting-ohdsi-athena-omop-cdm-vocabularies)
  - [Converting an External Mapping Source](#converting-an-external-mapping-source)
  - [Automated Pipeline Execution](#automated-pipeline-execution)
  - [Interactive Review Workflow](#interactive-review-workflow)
  - [Manual SSSOM Entry](#manual-sssom-entry)
  - [Synchronizing from the Mapping Commons Registry](#synchronizing-from-the-mapping-commons-registry)
- [Test Suite & Validation](#test-suite--validation)
- [Contributing Mappings via Pull Requests](#contributing-mappings-via-pull-requests)
  - [Adding New Mappings](#adding-new-mappings)
  - [Modifying Existing Mappings](#modifying-existing-mappings)
  - [Removing or Deprecating Mappings](#removing-or-deprecating-mappings)
  - [Pre-Submission Validation](#pre-submission-validation)
  - [Pull Request Checklist](#pull-request-checklist)
- [Registry Submission Guidelines](#registry-submission-guidelines)
- [License](#license)

---

## Overview

Ontological mappings often live in disparate, non-standardized formats:
- RDF/OWL ontologies and alignments (Turtle, RDF/XML, N-Triples, N3)
- Delimited text files and spreadsheets (CSV, TSV, Microsoft Excel `.xls` / `.xlsx`)
- Library and bibliographic classification systems (MARC 21 authority records)
- HTML web tables and archived mediation pages (e.g., ROMULUS, W3C/EC JRC)
- Data repositories and archives (Zenodo records via DOIs, ZIP archives such as WHO ICD-11 releases)

KOS-Mappings ingests any of these sources, enriches them with repository and platform metadata (via GitHub and SourceForge APIs), normalizes entities into CURIEs using controlled prefix maps, and emits standard SSSOM TSV files with embedded YAML header comments.

---

## Mapping Commons Registry Integration

The [Mapping Commons](https://mapping-commons.github.io/) initiative organizes distributed mapping sets adhering to FAIR principles. All canonical mapping files produced by this tool are organized in the `./commons` directory according to the standard pairwise prefix hierarchy:

```
commons/<subject_prefix>/<object_prefix>/<subject_prefix>_<object_prefix>.sssom.tsv
```

For example:
- `commons/dbo/sumo/dbo_sumo.sssom.tsv`: DBpedia Ontology (`dbo`) to Suggested Upper Merged Ontology (`sumo`)
- `commons/bibo/fabio/bibo_fabio.sssom.tsv`: Bibliographic Ontology (`bibo`) to FRBR-aligned Bibliographic Ontology (`fabio`)
- `commons/icd10cm/icd9cm/icd10cm_icd9cm.sssom.tsv`: ICD-10-CM to ICD-9-CM GEM mapping
- `commons/icd10/icd11/icd10_icd11.sssom.tsv`: WHO ICD-10 to ICD-11 Foundation/MMS mappings
- `commons/lcsh/mesh/lcsh_mesh.sssom.tsv`: Library of Congress Subject Headings (`lcsh`) to Medical Subject Headings (`mesh`)
- `commons/bfo/gfo/bfo_gfo.sssom.tsv`: Basic Formal Ontology (`bfo`) to General Formal Ontology (`gfo`)
- `commons/dcat/prov/dcat_prov.sssom.tsv`: Data Catalog Vocabulary (`dcat`) to W3C PROV-O (`prov`)

### SSSOM Standard Compliance & Metadata Quality

Each generated mapping file strictly adheres to the [SSSOM (Simple Standard for Sharing Ontological Mappings)](https://mapping-commons.github.io/sssom/) specification:

1. **Per-File Filtered CURIE Maps**:
   - Rather than dumping the entire repository-wide prefix catalog, each individual `.sssom.tsv` file strictly contains **only** the CURIE prefixes used by the entities, predicates, and provenance attributes mapped in that specific file (e.g. `doid`, `mesh`, `skos`, `semapv`, `orcid`).
   - Every CURIE in the table is guaranteed a valid namespace expansion without redundant or unused prefixes.

2. **Structure & Version Tracking**:
   - `subject_source`: Identifier or URI of the source ontology/terminology (e.g., `doid`, `icd10cm`, `lcsh`).
   - `subject_source_version`: Explicit version/release of the source structure (e.g., `"2026-07-31"`, `2018`, `2019`).
   - `object_source`: Identifier or URI of the target ontology/terminology (e.g., `mesh`, `icd9cm`, `icd11`).
   - `object_source_version`: Explicit version/release of the target structure (e.g., `2026`, `2017`, `"2024-01"`).
   - `mapping_set_version`: Version of the mapping set (e.g. release tag, git commit SHA `36853f75`, or publication release).
   - `mapping_tool` & `mapping_tool_version`: Provenance tool identification (e.g., `Biomappings`, `KOS-Mappings Pipeline 1.0.0`).

3. **Example Header**:
   ```tsv
   # curie_map:
   #   doid: "http://purl.obolibrary.org/obo/DOID_"
   #   mesh: "https://meshb.nlm.nih.gov/record/ui?ui="
   #   orcid: "https://orcid.org/"
   #   semapv: "https://w3id.org/semapv/vocab/"
   #   skos: "http://www.w3.org/2004/02/skos/core#"
   # license: "CC0-1.0"
   # mapping_date: "2026-11-02"
   # mapping_provider: "https://raw.githubusercontent.com/biopragmatics/biomappings/master/src/biomappings/resources/positive.sssom.tsv"
   # mapping_set_id: "https://w3id.org/commons/mappings/doid_mesh"
   # mapping_set_title: "DOID to MESH Mappings"
   # mapping_set_version: "2026-11-02"
   # mapping_tool: "Biomappings"
   # mapping_tool_version: "0.1.0"
   # object_source: "mesh"
   # object_source_version: "2026"
   # subject_source: "doid"
   # subject_source_version: "2026-07-31"
   ```

4. **Cumulative Totality & Self-Contained Row Metadata**:
   - Each canonical mapping file in `./commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv` represents the **totality of mappings** between the two platforms.
   - To support incremental updates where new rows are added to the same document at later dates (or from multiple upstream contributors), **every row contains full self-contained metadata**:
     - `subject_id`, `predicate_id`, `object_id`, `mapping_justification`
     - `subject_label`, `object_label`
     - `subject_source` & `subject_source_version` (e.g., `doid`, `2026-07-31`)
     - `object_source` & `object_source_version` (e.g., `mesh`, `2026`)
     - `mapping_tool` & `mapping_tool_version` (e.g., `Biomappings`, `0.1.0`)
     - `mapping_date` (exact date each mapping was curated or ingested)
     - `mapping_provider` (source URL/repository where the mapping originated)
     - `author_id` / `creator_id` (curator ORCIDs)
     - `license` (per-mapping license, e.g., `CC0-1.0`)
   - When new rows are ingested in the future, smart merging deduplicates by `(subject_id, predicate_id, object_id)` and preserves the exact provenance of both existing and newly added rows.

---

## Repository Size Limits & SSSOM Compression (.sssom.tsv.gz)

### Why Compression is Essential for GitHub Hosting

1. **GitHub Hard Limits & Warnings**:
   - GitHub **strictly blocks pushes** containing individual files larger than **100 MB**.
   - GitHub issues proactive warnings on pushes with files exceeding **50 MB**.
   - GitHub strongly recommends that total repository working trees remain below **1 GB to 5 GB** to prevent performance degradation during cloning, indexing, and delta compression.

2. **High-Density Crosswalk Tables**:
   - Comprehensive crosswalk tables (e.g. SNOMED CT, LOINC, ICD-10-PCS, SUMO-WordNet) often encompass tens of thousands to hundreds of thousands of mapping rows.
   - SSSOM TSV files contain repetitive CURIE prefixes (snomedct:, loinc:), predicates (skos:exactMatch), justifications (semapv:ManualMappingCuration), and provenance URLs across every row.

3. **Standard SSSOM Gzip Support (.sssom.tsv.gz)**:
   - The official [SSSOM specification](https://mapping-commons.github.io/sssom/) standardizes .sssom.tsv.gz as a first-class, interoperable file extension.
   - Standard DEFLATE/gzip compression typically achieves **85% to 92% file size reduction** on SSSOM TSV data:
     - A ~32 MB procedural alignment table compresses to **~3.5 MB**.
     - A ~10 MB laboratory alignment compresses to **~1.1 MB**.
   - KOS-Mappings transparently reads, merges, and writes both uncompressed .sssom.tsv and compressed .sssom.tsv.gz files:
     `ash
     # Generate or compress canonical files on write:
     python src/write_sssom_file.py <source> --compress
     `

---

## Vocabulary Endpoint Dictionary

To provide human-readable disambiguation of all 320+ CURIE prefixes, KOS-Mappings maintains canonical endpoint dictionaries:

- **endpoints.tsv**: Machine-readable tabular reference documenting:
  - prefix: Controlled lowercase CURIE prefix (e.g. mesh, loinc, snomedct, doid).
  - 
ame: Official long-form title (e.g. Medical Subject Headings, Logical Observation Identifiers Names and Codes).
  - category: Domain grouping (e.g. *Health & Biomedicine*, *OBO Ontologies*, *Upper Ontologies*, *Bibliographic Standards*).
  - uri_prefix: Canonical URI expansion pattern (e.g. http://id.nlm.nih.gov/mesh/).
  - uthority: Governance body (e.g. *National Library of Medicine*, *Regenstrief Institute*, *SNOMED International*).
  - description: Scope and domain coverage.
- **endpoints.txt**: Clean text dictionary for quick terminal cross-referencing and text search.
- **www/data/endpoints.json**: Pre-indexed endpoint registry powering the web explorer.

---

## Web Explorer & Semantic Pathfinder (./www)

The repository includes a modern, responsive web application located in ./www designed for deployment to **GitHub Pages**:

- **Crosswalk Pathfinder (Shortest Path & Hop-by-Hop Route Descriptor)**:
  - Discovers the closest mapping between any two vocabularies using graph Breadth-First-Search (BFS).
  - If a direct alignment exists, displays direct mapping metrics, predicates, and sample concept rows.
  - If no direct alignment exists, discovers the shortest multi-hop transitive bridge across intermediate ontologies (e.g., LOINC -> MESH -> SNOMED CT or DOID -> MONDO -> UMLS -> SNOMED CT).
  - Generates plain-English narrative path explanations explaining the semantic rationale behind each hop.
- **Concept & Mapping Query Engine**:
  - Live, instant search across concept labels, codes, and CURIEs.
  - Interactive filters by predicate (skos:exactMatch, skos:broadMatch), source ontology, and target ontology.
- **Vocabulary Directory**:
  - Searchable card directory of all 320+ endpoints with authorities, categories, and URI expansions.
- **Automated CI/CD Deployment**:
  - Backed by .github/workflows/deploy-pages.yml which automatically aggregates all mapping tables, compiles www/data/mappings_graph.json, and deploys to GitHub Pages upon push to main.

---

## Repository Structure

```
KOS-Mappings/
├── .gitignore                      # Clean ignore rules for builds, envs, and temporary test outputs
├── requirements.txt                # Production and testing dependencies
├── README.md                       # Repository overview and documentation
├── endpoints.tsv                   # Machine-readable tabular dictionary of 320+ vocabulary endpoints
├── endpoints.txt                   # Human-readable reference listing long-form endpoint names
├── .github/
│   └── workflows/
│       └── deploy-pages.yml        # CI/CD automated deployment of web application to GitHub Pages
├── commons/                        # Canonical Mapping Commons output directory
│   ├── dbo/sumo/dbo_sumo.sssom.tsv
│   ├── bibo/fabio/bibo_fabio.sssom.tsv
│   ├── icd10cm/icd9cm/icd10cm_icd9cm.sssom.tsv
│   ├── lcsh/mesh/lcsh_mesh.sssom.tsv
│   ├── bfo/gfo/bfo_gfo.sssom.tsv
│   ├── loinc/snomedct/loinc_snomedct.sssom.tsv
│   ├── snomedct/ucum/snomedct_ucum.sssom.tsv
│   ├── snomedct/omopext/snomedct_omopext.sssom.tsv
│   └── ...                         # Pairwise ontology mapping collections
├── src/
│   ├── __init__.py                 # Source package marker
│   ├── build_web_index.py          # Web graph indexer: scans commons/ into JSON for web app
│   ├── generate_endpoints_reference.py # Generates endpoints.tsv, endpoints.txt, and endpoints.json
│   ├── generate_sssom_metadata.py  # Dispatcher: selects loaders, enriches platform metadata, builds JSON
│   ├── review_sssom_metadata.py    # Review UI / pipeline confirming metadata and recording review audit
│   ├── write_sssom_file.py         # Orchestrator: performs smart merge & writes canonical SSSOM TSVs
│   ├── sync_mapping_commons_registry.py # Sync utility: ingests official Mapping Commons Registry sets
│   ├── load_from_athena.py         # Loader for OHDSI Athena (OMOP CDM v5) vocabulary archives
│   ├── load_from_graph.py          # Loader for RDF/OWL/Turtle/NTriples/N3 graphs
│   ├── load_from_sssom.py          # Loader for pre-existing SSSOM TSV files
│   ├── load_from_spreadsheet.py    # Loader for Excel (.xls, .xlsx), CSV, and TSV tables
│   ├── load_from_webpage.py        # Scraper/loader for HTML tables (including ROMULUS alignment pages & JRC)
│   ├── load_from_document.py       # Loader for MARC records, ZIP archives, and DOI/Zenodo resolutions
│   ├── load_from_manual_input.py   # Interactive CLI tool for manual SSSOM mapping entry
│   ├── load_tables_from_document.py# Table extractor for PDF, DOCX, and scanned documents
│   ├── load_thesaurus_from_document.py # SKOS extractor for PDF thesauri
│   ├── ingest_sssom_archive.py     # Streaming ingester for SSSOM tarball archives (.tgz)
│   ├── retrieve_github_metadata.py # GitHub REST API metadata & commit contributor scraper
│   └── retrieve_sourceforge_metadata.py # SourceForge API & SVN file history scraper
├── www/                            # Static web application (GitHub Pages deployment)
│   ├── index.html                  # Responsive UI: Pathfinder, Query Engine, Endpoints Directory, Topology
│   ├── css/
│   │   └── style.css               # Rich modern dark theme with glassmorphism & responsive grid
│   ├── js/
│   │   └── app.js                  # Client-side BFS shortest path algorithm & mapping query engine
│   └── data/
│       ├── mappings_graph.json     # Graph topology & pre-indexed mapping samples
│       └── endpoints.json          # Complete 320+ vocabulary endpoint registry
└── test/
    ├── __init__.py                 # Test package marker
    ├── test_urls.txt               # Canonical test benchmark URLs
    ├── run_urls_test.py            # Comprehensive integration test driver (generates report.json)
    └── test_loaders.py             # Pytest unit test suite for loaders and SSSOM output validation
```

---

## Supported Formats & Loaders

| Loader Module | Source Types & Extensions | Example Sources |
|---|---|---|
| `load_from_athena.py` | OHDSI Athena (OMOP CDM v5) ZIP archives and directories (`VOCABULARY.csv`, `CONCEPT.csv`, `CONCEPT_RELATIONSHIP.csv`) | Athena vocabulary bundles (e.g. SNOMED CT, LOINC, UCUM, OMOP Extension, RxNorm, MeSH, ICD-10) |
| `load_from_graph.py` | Turtle (`.ttl`), RDF/XML (`.rdf`, `.owl`, `.xml`), N-Triples (`.nt`), N3 (`.n3`) | SUMO-DBpedia, BIBO2SPAR, DCAT-PROV, SIO-RO Bridge OWL, Schema.org Turtle, BFO-Mappings PROV-to-BFO with OWL 2 annotated axioms |
| `load_from_sssom.py` | SSSOM TSV (`.sssom.tsv`, `.sssom`) | Biomappings `positive.sssom.tsv` |
| `load_from_spreadsheet.py` | Microsoft Excel (`.xlsx`, `.xls`), CSV (`.csv`), TSV (`.tsv`) | CMS/NBER GEM forward & reverse diagnosis and procedure mappings (`icd10cmtoicd9`, `icd9toicd10cm`, `icd10pcstoicd9`, `icd9toicd10pcs`), EBSCO QRH Coverage List |
| `load_from_webpage.py` | HTML web pages, ARIA data tables, Wayback Machine archives | EC JRC DCAT-AP to Schema.org, EC JRC DataCite to DCAT-AP, W3C Dublin Core to PROV (`prov-dc`), ROMULUS multi-ontology alignment metadata (BFO, GFO, DOLCE-Lite) |
| `load_from_document.py` | MARC 21 Authority files, ZIP bundles, DOIs / Zenodo datasets | Galter LCSH-to-MeSH cross-referenced MARC, WHO ICD-11 ZIP, RDA DOI |
| `ingest_sssom_archive.py` | Compressed SSSOM TAR archives (`.tgz`, `.tar.gz`) | OLS4 SSSOM bulk extracts (`sssom.tgz`) |
| `load_from_manual_input.py` | Interactive terminal input | Ad-hoc domain curation |

---

## Installation

### Prerequisites
- Python 3.9 or higher
- Git

### Setup
```bash
# Clone the repository
git clone https://github.com/Superraptor/KOS-Mappings.git
cd KOS-Mappings

# Create and activate a virtual environment (optional but recommended)
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

---

## Quick Start

Convert a mapping source into the `./commons` registry structure with a single command:

```bash
# Process an online Turtle mapping non-interactively
python src/write_sssom_file.py "https://raw.githubusercontent.com/ontologyportal/sumo/master/mappings/DBpediaMapping.ttl" -y --no-edit

# Process an online CSV crosswalk
python src/write_sssom_file.py "https://data.nber.org/gem/icd10cmtoicd9gem.csv" -y --no-edit

# Process a MARC authority mapping file (with MeSH/LCSH cross-referencing and predicate detection)
python src/write_sssom_file.py "https://raw.githubusercontent.com/galterlibrary/mapping-project/master/LCSH-to-MeSH-mapping-data.txt" -y --no-edit

# Process all 20 ROMULUS ontology alignment metadata pages
python src/write_sssom_file.py "https://web.archive.org/web/20180102005419id_/http://www.thezfiles.co.za/ROMULUS/ontologyAlignmentMetadata.html" -y --no-edit

# Ingest SSSOM tarball archive into canonical commons/ structure
python src/ingest_sssom_archive.py --archive "C:\Users\clair\Downloads\sssom.tgz" --max-files 50
```

The resulting files will be placed under `./commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv`.

---

## Usage Guide

### Converting an External Mapping Source

```bash
python src/write_sssom_file.py <URL_OR_FILEPATH> [OPTIONS]
```

#### Options:
- `-y`, `--yes`: Automatically accept metadata review prompts without blocking.
- `--no-edit`: Skip opening an interactive text editor to edit metadata JSON.
- `-o <PATH>`, `--output <PATH>`: Write an additional copy of the merged output to the specified file path.

### Automated Pipeline Execution

For continuous integration (CI) workflows, use `-y` and `--no-edit`:

```bash
python src/write_sssom_file.py https://example.org/mappings.ttl -y --no-edit
```

### Interactive Review Workflow

If run without `-y`, `write_sssom_file.py` displays the generated SSSOM metadata and prompts for confirmation:
1. Review the generated CURIE prefix map, license, and dataset details.
2. Optionally open your `$EDITOR` (or Notepad / vi) to modify any field.
3. Supply reviewer attribution to be recorded in the audit trail.
4. The tool merges rows into the canonical `./commons` file using smart deduplication.

### Manual SSSOM Entry

To manually curate mapping triples through an interactive prompt:

```bash
python src/load_from_manual_input.py -o manual.sssom.tsv
```

### Synchronizing from the Mapping Commons Registry

KOS-Mappings includes a dedicated registry synchronization utility (`src/sync_mapping_commons_registry.py`) that queries the live Mapping Commons specifications catalog at [https://mapping-commons.github.io/data/mapping-specifications.json](https://mapping-commons.github.io/data/mapping-specifications.json), downloads published SSSOM mapping files, and harmonizes them into `./commons`:

```bash
# 1. Discover all registered initiatives and available SSSOM mapping files
python src/sync_mapping_commons_registry.py --list

# 2. Preview mappings for a specific registry community (dry-run mode)
python src/sync_mapping_commons_registry.py --registry "Mouse Human" --dry-run

# 3. Ingest and merge all mappings from an initiative into canonical ./commons files
python src/sync_mapping_commons_registry.py --registry "Mouse Human Mapping Initiative"

# 4. Ingest a limited batch of specifications (e.g., first 5)
python src/sync_mapping_commons_registry.py --registry "Monarch" --limit 5

# 5. Ingest all available SSSOM specifications across all Mapping Commons initiatives
python src/sync_mapping_commons_registry.py --all
```

**Features during synchronization**:
- Automatically groups and merges multi-file initiatives between the same ontologies into a single cumulative canonical file (e.g. multiple MP-to-HP files seamlessly merge into `commons/mp/hp/mp_hp.sssom.tsv`).
- Populates every row with self-contained provenance, structure release versions, and curator attribution.
- Dynamically filters the `# curie_map:` in each target file to only include the prefixes referenced by the mapped entities.

---

## Test Suite & Validation

The test suite validates loaders and end-to-end conversions across 13 diverse mapping formats.

### 1. Run Unit Tests (Pytest)

```bash
pytest test/test_loaders.py -v
```

### 2. Run Comprehensive URL Test Suite

```bash
python test/run_urls_test.py
```

The driver executes all URLs in `test/test_urls.txt`, checks exit codes, generates SSSOM files, and writes a detailed report to `test/tmp-sssom-run-<timestamp>/report.json`.

```
============================================================
Test Suite Summary: 13 / 13 Succeeded (100% Pass Rate)
============================================================
✔ 001/013: DBpediaMapping.ttl                     (Turtle / GitHub)
✔ 002/013: BIBO2SPAR.ttl                          (Turtle / SourceForge)
✔ 003/013: bibo.ttl                               (Turtle / Schema.org)
✔ 004/013: SUMO.owl                               (OWL / RDF-XML)
✔ 005/013: dcat-ap-to-schema-org                  (HTML Webpage)
✔ 006/013: positive.sssom.tsv                     (Biomappings SSSOM)
✔ 007/013: dcat-prov.ttl                          (W3C NS Turtle)
✔ 008/013: mapping.zip                            (WHO ICD-11 ZIP)
✔ 009/013: icd10cmtoicd9gem.csv                   (NBER GEM CSV)
✔ 010/013: LCSH-to-MeSH-mapping-data.txt          (MARC 21 Text)
✔ 011/013: qrh-coverage.xls                       (Excel .xls)
✔ 012/013: 10.15497/RDA00069                      (Zenodo DOI .xls)
✔ 013/013: bfo-gfobasic-metadata.php              (Wayback HTML)
============================================================
```

### 3. Validating Output Files with SSSOM-py

You can validate any file in `./commons` using the official `sssom` Python package:

```bash
python -c "import sssom.parsers; mdf = sssom.parsers.parse_sssom_table('commons/dbo/sumo/dbo_sumo.sssom.tsv'); print('Valid! Rows:', len(mdf.df))"
```

---

## Contributing Mappings via Pull Requests

We welcome contributions from the community! Whether you are adding new mappings between vocabularies, correcting an existing mapping relationship, updating metadata and provenance, or removing false positives, contributions are submitted via GitHub Pull Requests to [https://github.com/Superraptor/KOS-Mappings/](https://github.com/Superraptor/KOS-Mappings/).

### Repository Philosophy: Totality & Self-Contained Provenance

Before contributing, please keep two key principles in mind:
1. **Single Cumulative Totality**: Each file `commons/<subject_prefix>/<object_prefix>/<subject_prefix>_<object_prefix>.sssom.tsv` is the single, canonical source of truth for **all** mappings between those two vocabularies. New mappings between those structures are merged into that file rather than creating separate disjoint documents.
2. **Self-Contained Row Provenance**: Because rows in a file may come from multiple tools, dates, or contributors over time, **each row must be self-contained**, carrying its own `mapping_justification`, source/target versions, `mapping_tool`, `mapping_date`, and curator attribution (`author_id` / `creator_id`).
3. **Filtered CURIE Maps**: SSSOM headers should only define prefixes that are actually used in that file.

---

### Adding New Mappings

There are three ways to add mappings to the repository:

#### Method A: Automated Ingestion via Pipeline (Recommended for Datasets)
If you have an external alignment file, ontology, table, or URL (Turtle, RDF/XML, Excel, CSV, TSV, MARC, or SSSOM), use the built-in ingestion CLI:

```bash
# 1. Ingest an external URL or local file (smart-merges directly into ./commons)
python src/write_sssom_file.py "https://example.org/new_mappings.ttl" -y --no-edit

# 2. Or run interactive mode to preview and adjust metadata before writing:
python src/write_sssom_file.py "path/to/my_mappings.xlsx"
```
The pipeline automatically:
- Identifies the source format and extracts mapping pairs.
- Fetches upstream repository and release metadata via GitHub/SourceForge APIs.
- Resolves entity URIs to standardized CURIE prefixes.
- Deduplicates against existing mappings in `./commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv`.
- Formats multi-valued fields with standard pipe (`|`) delimiters.
- Filters `# curie_map:` to only the prefixes present in the resulting file.

#### Method B: Direct Row Addition
If you are adding a few curated mappings by hand:
1. Locate (or create) the target file at `commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv`.
2. Append new rows following the tab-separated column structure.
3. Ensure all mandatory fields are populated:
   - `subject_id`: Source CURIE (e.g. `mondo:0005015`)
   - `predicate_id`: Standard SKOS/OWL predicate (`skos:exactMatch`, `skos:closeMatch`, `skos:broadMatch`, `skos:narrowMatch`, `owl:equivalentClass`, `rdfs:subClassOf`)
   - `object_id`: Target CURIE (e.g. `doid:10652`)
   - `mapping_justification`: Single SEMAPV CURIE (e.g. `semapv:ManualMappingCuration`, `semapv:LexicalMatching`)
   - `author_id` / `creator_id`: Your ORCID (`orcid:0000-...`) or email (`mailto:...`)
   - `mapping_date`: Date formatted as `YYYY-MM-DD`
   - `license`: Canonical license identifier (e.g. `CC0-1.0`)
4. Verify that any newly introduced prefixes are defined in the YAML `# curie_map:` header.

#### Method C: Interactive CLI Curation
```bash
python src/load_from_manual_input.py -o manual.sssom.tsv
python src/write_sssom_file.py manual.sssom.tsv -y --no-edit
```

---

### Modifying Existing Mappings

If you find a mapping that needs improvement (e.g., refining an approximate match to an exact match, adding missing labels, or updating curator provenance):

1. **Locate the Row**: Open the canonical file `commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv` and find the row by its `(subject_id, predicate_id, object_id)`.
2. **Refine Predicates**:
   - Upgrade from `skos:closeMatch` to `skos:exactMatch` when concepts are verified to be clinically or conceptually equivalent.
   - Use `skos:broadMatch` (subject is narrower than object) or `skos:narrowMatch` (subject is broader than object) for asymmetrical mappings.
3. **Upgrade Justification**:
   - When human curation verifies an automated match, update `mapping_justification` to `semapv:ManualMappingCuration`. Note that SSSOM specifications require a single CURIE for `mapping_justification`.
4. **Add Commentary**:
   - Document your rationale or review findings in the `comment` column (e.g., `comment: Verified exact conceptual equivalence in 2026 nosology review`).
5. **Add Curator Attribution**:
   - Add your ORCID to `author_id` or `reviewer_id` (e.g. `orcid:0000-0002-1825-0097`). Multiple curators are separated with pipes `|`.

---

### Removing or Deprecating Mappings

If an existing mapping is determined to be a false positive or invalid:

- **Complete Deletion**: Remove the corresponding row from the `.sssom.tsv` file.
- **Negative / Disjoint Assertions**: If you wish to explicitly record that two concepts are disjoint or non-mappable (preventing future automated tools from falsely re-asserting equivalence), retain the row and set:
  - `predicate_id: owl:disjointWith`
  - `mapping_justification: semapv:ManualMappingCuration`
  - `comment: Mappable: No. Incompatible domain semantics verified.`

---

### Pre-Submission Validation

Before opening a pull request, run the test and validation suite locally:

```bash
# 1. Run unit tests
pytest test/test_loaders.py -v

# 2. Run integration tests (validates all canonical sources)
python test/run_urls_test.py

# 3. Validate your modified SSSOM TSV file with sssom-py
python -c "import sssom.parsers; mdf = sssom.parsers.parse_sssom_table('commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv'); print('Validated! Rows:', len(mdf.df))"
```

---

### Pull Request Checklist

When submitting your pull request to [https://github.com/Superraptor/KOS-Mappings/](https://github.com/Superraptor/KOS-Mappings/):

1. **Branch**: Create a feature branch off `main` (e.g., `git checkout -b update-bfo-gfo`).
2. **Commit Message**: Use a concise, descriptive commit title (e.g., `feat(mappings): add SNOMED to ICD-10 crosswalks` or `fix(commons): refine bfo_gfo predicates to exactMatch`).
3. **PR Description**: Include:
   - What ontologies or vocabularies are affected.
   - Summary of changes (added, modified, or removed rows).
   - Upstream source or authority references.
4. **Automated Checks**: Verify all tests pass (`pytest test/test_loaders.py -v`).

---

## Registry Submission Guidelines

To include mappings from this repository in the [Mapping Commons Registry](https://mapping-commons.github.io/):

1. **Verify SSSOM Conformance**: Ensure all target files under `./commons` validate cleanly with `sssom validate`.
2. **Persistent Identifier**: Each mapping set receives a canonical `mapping_set_id` (e.g., `https://w3id.org/commons/mappings/<p1>_<p2>`).
3. **Register Mapping Repository**:
   - Add this repository or specific `.sssom.tsv` raw URLs to the Mapping Commons `mapping-server.yml` configuration:
     ```yaml
     - id: kos-mappings-dbo-sumo
       name: DBpedia to SUMO Mappings
       url: https://raw.githubusercontent.com/Superraptor/KOS-Mappings/main/commons/dbo/sumo/dbo_sumo.sssom.tsv
       license: CC0-1.0
     ```
4. **Submit Pull Request**: Open a pull request against [mapping-commons/mapping-commons.github.io](https://github.com/mapping-commons/mapping-commons.github.io).

---

## License & Constituent Provenance

The code in this repository is distributed under the [MIT License](https://opensource.org/licenses/MIT).

### Constituent License Inheritance
KOS-Mappings preserves upstream intellectual property and licensing rights for all ingested mappings:
- **No Blanket Assumptions**: Mappings do not default to CC0 1.0. Every constituent mapping set and row inherits the license explicitly declared by its upstream authority, ontology graph, document, or repository API.
- **Inherited Upstream Licenses**:
  - **Public Domain Mark 1.0**: CMS / CDC General Equivalence Mappings (GEM)
  - **CC-BY 4.0**: European Commission JRC Crosswalks (DataCite to DCAT-AP, DCAT-AP to Schema.org), SIO-RO Bridge
  - **CC-BY 2.5**: BIBO2SPAR
  - **CC-BY-SA 3.0**: Schema.org
  - **W3C Software and Document Notice**: W3C DCAT-PROV, W3C PROV-DC
  - **CC0 1.0**: BFO-Mappings PROV-to-BFO, OBO Relations Ontology, Basic Formal Ontology
  - **Terms of Use**: EBSCO QRH title lists
  - **Unspecified**: Where an upstream source does not provide an explicit machine-readable license, the license is set to `https://w3id.org/sssom/license/unspecified` rather than assuming a permissive license.