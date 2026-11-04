# KOS-Mappings

[![Live Web Explorer](https://img.shields.io/badge/GitHub_Pages-Live_Explorer-00b4d8?logo=github)](https://superraptor.github.io/KOS-Mappings/)
[![SSSOM Standard](https://img.shields.io/badge/SSSOM-v1.0-blue.svg)](https://mapping-commons.github.io/sssom/)
[![Mapping Commons](https://img.shields.io/badge/Registry-Mapping_Commons-green.svg)](https://mapping-commons.github.io/)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/Code_License-MIT-lightgrey.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-23%2F23%20passing-brightgreen.svg)](test/test_loaders.py)

**KOS-Mappings** is an automated extraction, parsing, and harmonization toolkit for Knowledge Organization Systems (KOS), ontologies, thesauri, vocabulary crosswalks, and alignment tables. It converts diverse source formats into validated, high-quality [Simple Standard for Sharing Ontological Mappings (SSSOM)](https://mapping-commons.github.io/sssom/) TSV files structured for publication in the [Mapping Commons Registry](https://mapping-commons.github.io/).

> **Explore Mappings Online:** The interactive **KOS-Mappings Web Explorer & Semantic Pathfinder** is live on GitHub Pages at **[https://superraptor.github.io/KOS-Mappings/](https://superraptor.github.io/KOS-Mappings/)**.

---

## Table of Contents

- [Overview](#overview)
- [Mapping Commons Registry Integration](#mapping-commons-registry-integration)
  - [SSSOM Standard Compliance & Metadata Quality](#sssom-standard-compliance--metadata-quality)
- [Repository Size Limits & SSSOM Compression (`.sssom.tsv.gz`)](#repository-size-limits--sssom-compression-sssomtsvgz)
- [Vocabulary Endpoint Dictionary](#vocabulary-endpoint-dictionary)
- [Web Explorer & GitHub Pages Deployment (`./www`)](#web-explorer--github-pages-deployment-www)
  - [Live GitHub Pages Site](#live-github-pages-site)
  - [Interactive Capabilities](#interactive-capabilities)
  - [Automated GitHub Pages CI/CD Pipeline](#automated-github-pages-cicd-pipeline)
  - [Building & Previewing the Site Locally](#building--previewing-the-site-locally)
  - [Enabling GitHub Pages on a Fork](#enabling-github-pages-on-a-fork)
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
- [License & Constituent Provenance](#license--constituent-provenance)

---

## Overview

Ontological mappings often live in disparate, non-standardized formats:
- **RDF/OWL ontologies and alignments** (Turtle, RDF/XML, N-Triples, N3, OWL 2 annotated axioms)
- **Clinical terminology repositories** (OHDSI Athena / OMOP CDM v5 `CONCEPT.csv` and `CONCEPT_RELATIONSHIP.csv` bundles)
- **Delimited text files and spreadsheets** (CSV, TSV, Microsoft Excel `.xls` / `.xlsx`)
- **Library and bibliographic classification systems** (MARC 21 authority records)
- **HTML web tables and archived mediation pages** (e.g., ROMULUS, W3C, European Commission JRC)
- **Data repositories and archives** (Zenodo records via DOIs, OLS4 `.tgz` archives, WHO ICD-11 release ZIPs)

**KOS-Mappings** ingests any of these sources, enriches them with repository and platform metadata (via GitHub and SourceForge APIs), normalizes entities into CURIEs using controlled prefix maps, and emits standard SSSOM TSV files with embedded YAML header comments.

---

## Mapping Commons Registry Integration

The [Mapping Commons](https://mapping-commons.github.io/) initiative organizes distributed mapping sets adhering to FAIR principles. All canonical mapping files produced by this toolkit are organized in the `./commons` directory according to the standard pairwise prefix hierarchy:

```text
commons/<subject_prefix>/<object_prefix>/<subject_prefix>_<object_prefix>.sssom.tsv[.gz]
```

Representative examples:
- `commons/dbo/sumo/dbo_sumo.sssom.tsv`: DBpedia Ontology (`dbo`) to Suggested Upper Merged Ontology (`sumo`)
- `commons/bibo/fabio/bibo_fabio.sssom.tsv`: Bibliographic Ontology (`bibo`) to FRBR-aligned Bibliographic Ontology (`fabio`)
- `commons/icd10cm/icd9cm/icd10cm_icd9cm.sssom.tsv`: ICD-10-CM to ICD-9-CM General Equivalence Mappings (GEM)
- `commons/icd10/icd11/icd10_icd11.sssom.tsv`: WHO ICD-10 to ICD-11 Foundation/MMS mappings
- `commons/lcsh/mesh/lcsh_mesh.sssom.tsv`: Library of Congress Subject Headings (`lcsh`) to Medical Subject Headings (`mesh`)
- `commons/loinc/snomedct/loinc_snomedct.sssom.tsv`: LOINC laboratory/clinical observations (`loinc`) to SNOMED CT (`snomedct`)
- `commons/bfo/gfo/bfo_gfo.sssom.tsv`: Basic Formal Ontology (`bfo`) to General Formal Ontology (`gfo`)
- `commons/dcat/prov/dcat_prov.sssom.tsv`: Data Catalog Vocabulary (`dcat`) to W3C PROV-O (`prov`)

### SSSOM Standard Compliance & Metadata Quality

Each generated mapping file strictly adheres to the [SSSOM (Simple Standard for Sharing Ontological Mappings)](https://mapping-commons.github.io/sssom/) specification:

1. **Per-File Filtered CURIE Maps**:
   - Rather than dumping the entire repository-wide prefix catalog, each `.sssom.tsv` file contains **only** the CURIE prefixes used by the entities, predicates, and provenance attributes mapped in that specific file (e.g., `doid`, `mesh`, `skos`, `semapv`, `orcid`).
   - Every CURIE in the table is guaranteed a valid namespace expansion without redundant or unused prefixes.

2. **Structure & Version Tracking**:
   - `subject_source`: Identifier or URI of the source ontology/terminology (e.g., `doid`, `icd10cm`, `lcsh`).
   - `subject_source_version`: Explicit version or release of the source structure (e.g., `"2026-07-31"`, `"2018"`, `"2019"`).
   - `object_source`: Identifier or URI of the target ontology/terminology (e.g., `mesh`, `icd9cm`, `icd11`).
   - `object_source_version`: Explicit version or release of the target structure (e.g., `"2026"`, `"2017"`, `"2024-01"`).
   - `mapping_set_version`: Version of the mapping set (e.g., release tag, git commit SHA, or publication date).
   - `mapping_tool` & `mapping_tool_version`: Provenance tool identification (e.g., `Biomappings`, `KOS-Mappings Pipeline 1.0.0`).

3. **Example Header**:
   ```yaml
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
   - Each canonical mapping file in `./commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv` represents the **totality of mappings** between the two vocabularies.
   - To support incremental updates where new rows are added at later dates or from multiple upstream contributors, **every row contains full self-contained metadata**:
     - `subject_id`, `predicate_id`, `object_id`, `mapping_justification`
     - `subject_label`, `object_label`
     - `subject_source` & `subject_source_version`
     - `object_source` & `object_source_version`
     - `mapping_tool` & `mapping_tool_version`
     - `mapping_date` (authentic origination date derived from the source artifact or commit history)
     - `mapping_provider` (source URL/repository where the mapping originated)
     - `author_id` / `creator_id` (curator ORCIDs or identifiers)
     - `license` (per-mapping inherited license)
   - When new rows are ingested, smart merging deduplicates by `(subject_id, predicate_id, object_id)` and preserves the provenance of both existing and newly added rows.

---

## Repository Size Limits & SSSOM Compression (`.sssom.tsv.gz`)

### Why Compression is Essential for GitHub Hosting

1. **GitHub Hard Limits & Warnings**:
   - GitHub **strictly blocks pushes** containing individual files larger than **100 MB**.
   - GitHub issues warnings on pushes with files exceeding **50 MB**.
   - GitHub recommends keeping total repository working trees below **1 GB to 5 GB** for fast cloning, indexing, and CI runs.

2. **High-Density Crosswalk Tables**:
   - Comprehensive clinical and lexical crosswalk tables (e.g., SNOMED CT, LOINC, ICD-10-PCS, SUMO-WordNet) frequently contain tens of thousands to hundreds of thousands of mapping rows.
   - SSSOM TSV files repeat CURIE prefixes (`snomedct:`, `loinc:`), predicates (`skos:exactMatch`), justifications (`semapv:ManualMappingCuration`), and provenance URLs across every row.

3. **Standard SSSOM Gzip Support (`.sssom.tsv.gz`)**:
   - The official [SSSOM specification](https://mapping-commons.github.io/sssom/) standardizes `.sssom.tsv.gz` as a first-class, interoperable file extension.
   - Standard DEFLATE/gzip compression typically achieves **85% to 92% file size reduction** on SSSOM TSV data:
     - A ~32 MB procedural alignment table compresses to **~3.5 MB**.
     - A ~10 MB laboratory alignment compresses to **~1.1 MB**.
   - KOS-Mappings transparently reads, merges, indexes, and writes both uncompressed `.sssom.tsv` and compressed `.sssom.tsv.gz` files:
     ```bash
     # Generate or compress canonical files on write:
     python src/write_sssom_file.py <source> --compress
     ```

---

## Vocabulary Endpoint Dictionary

To provide human-readable disambiguation across all 325+ CURIE prefixes, KOS-Mappings maintains canonical endpoint dictionaries generated via `src/generate_endpoints_reference.py`:

- **`endpoints.tsv`**: Machine-readable tabular reference documenting:
  - `prefix`: Controlled lowercase CURIE prefix (e.g., `mesh`, `loinc`, `snomedct`, `doid`).
  - `name`: Official long-form title (e.g., *Medical Subject Headings*, *Logical Observation Identifiers Names and Codes*).
  - `category`: Domain grouping (e.g., *Health & Biomedicine*, *OBO Ontologies*, *Upper Ontologies*, *Bibliographic Standards*).
  - `uri_prefix`: Canonical URI expansion pattern (e.g., `http://id.nlm.nih.gov/mesh/`).
  - `authority`: Governance body (e.g., *National Library of Medicine*, *Regenstrief Institute*, *SNOMED International*).
  - `description`: Scope and domain coverage summary.
- **`endpoints.txt`**: Formatted plain-text reference for quick terminal cross-referencing and search.
- **`www/data/endpoints.json`**: Pre-indexed JSON endpoint registry powering the GitHub Pages web explorer.

---

## Web Explorer & GitHub Pages Deployment (`./www`)

### Live GitHub Pages Site

The interactive **KOS-Mappings Explorer** is published via GitHub Pages at:

**[https://superraptor.github.io/KOS-Mappings/](https://superraptor.github.io/KOS-Mappings/)**

### Interactive Capabilities

The static web application in `./www` provides four interactive views over the repository's 325+ vocabularies, 532+ pairwise mapping sets, and 790,000+ curated mappings:

1. **Semantic Crosswalk Pathfinder (Shortest Path & Hop-by-Hop Route Descriptor)**:
   - Discovers the closest alignment route between any two vocabularies using client-side Breadth-First Search (BFS) over the registry graph.
   - **Direct Alignments (1 Hop)**: Displays total mapping count, dominant predicates, direct link to the canonical `.sssom.tsv` / `.sssom.tsv.gz` file on GitHub, and sample concept pairs.
   - **Transitive Bridges (Multi-Hop)**: Automatically finds the shortest multi-hop bridge across intermediate hub ontologies (e.g., `LOINC -> SNOMED CT -> UCUM` or `DOID -> MONDO -> SNOMED CT`) when no direct crosswalk file exists.
   - Generates a plain-English narrative explaining each hop and supports one-click copying of the path summary.
2. **Live Concept & Mapping Query Engine**:
   - Instant client-side search across representative concept labels, codes, and CURIEs.
   - Interactive filtering by predicate (`skos:exactMatch`, `skos:broadMatch`, `skos:closeMatch`, `skos:narrowMatch`, `owl:equivalentClass`) as well as source and target vocabularies.
3. **Vocabulary Endpoint Dictionary**:
   - Searchable card directory of all 325+ registered endpoints with domain category pills (*Health & Biomedicine*, *OBO Ontologies*, *Upper Ontologies*, *Bibliographic*, *Geographic*), governing authorities, and URI prefixes.
4. **Registry Topology & Global Metrics**:
   - Global counts of registered vocabularies, pairwise alignment sets, and total validated mappings.
   - Centrality rankings highlighting the most connected hub vocabularies and a sortable pairwise file matrix linking directly to each `.sssom.tsv` file on GitHub.

### Automated GitHub Pages CI/CD Pipeline

Deployment to GitHub Pages is fully automated via [`.github/workflows/deploy-pages.yml`](.github/workflows/deploy-pages.yml):

- **Triggers**:
  - Automatically runs on every push to `main` that modifies `commons/**`, `src/**`, `www/**`, `endpoints.*`, or `.github/workflows/deploy-pages.yml`.
  - Can also be triggered manually at any time from the GitHub **Actions** tab via `workflow_dispatch`.
- **Build & Deploy Steps**:
  1. Checks out the repository and sets up Python 3.11 with pip caching.
  2. Executes `python src/build_web_index.py`, which regenerates `endpoints.tsv`, `endpoints.txt`, `www/data/endpoints.json`, and scans all `.sssom.tsv` and `.sssom.tsv.gz` files in `./commons/` to compile `www/data/mappings_graph.json`.
  3. Packages the `./www` directory using `actions/upload-pages-artifact@v3` and deploys it to GitHub Pages via `actions/deploy-pages@v4`.

### Building & Previewing the Site Locally

To rebuild the web index after adding or modifying mappings in `./commons` and preview the site locally:

```bash
# 1. Rebuild www/data/mappings_graph.json and www/data/endpoints.json
python src/build_web_index.py

# 2. Serve ./www locally over HTTP
python -m http.server 8000 --directory www
```

Then open `http://localhost:8000` in your browser. *(Note: Opening `www/index.html` directly via `file://` is blocked by browser CORS policies when fetching the JSON data files; always use a local HTTP server.)*

### Enabling GitHub Pages on a Fork

If you fork this repository and want to publish your own instance of the Web Explorer on GitHub Pages:
1. Navigate to your repository on GitHub and open **Settings** &rarr; **Pages**.
2. Under **Build and deployment** &rarr; **Source**, select **GitHub Actions**.
3. Push a commit to `main` or manually trigger **Deploy KOS-Mappings Web Explorer to GitHub Pages** under the **Actions** tab.

---

## Repository Structure

```text
KOS-Mappings/
├── .gitignore                          # Ignore rules for virtualenvs, build caches, and temp outputs
├── requirements.txt                    # Production and testing Python dependencies
├── README.md                           # Repository documentation and usage guide
├── endpoints.tsv                       # Machine-readable tabular dictionary of 325+ vocabulary endpoints
├── endpoints.txt                       # Human-readable reference listing long-form endpoint names
├── .github/
│   └── workflows/
│       └── deploy-pages.yml            # CI/CD workflow building the graph index and deploying to GitHub Pages
├── commons/                            # Canonical Mapping Commons output directory
│   ├── dbo/sumo/dbo_sumo.sssom.tsv
│   ├── bibo/fabio/bibo_fabio.sssom.tsv
│   ├── icd10cm/icd9cm/icd10cm_icd9cm.sssom.tsv
│   ├── lcsh/mesh/lcsh_mesh.sssom.tsv
│   ├── bfo/gfo/bfo_gfo.sssom.tsv
│   ├── loinc/snomedct/loinc_snomedct.sssom.tsv
│   ├── snomedct/ucum/snomedct_ucum.sssom.tsv
│   └── ...                             # 530+ pairwise ontology mapping sets (.sssom.tsv and .sssom.tsv.gz)
├── src/
│   ├── __init__.py                     # Source package marker
│   ├── build_web_index.py              # Web graph indexer: compiles commons/ into JSON for ./www
│   ├── generate_endpoints_reference.py # Generates endpoints.tsv, endpoints.txt, and www/data/endpoints.json
│   ├── generate_sssom_metadata.py      # Dispatcher: selects loaders, enriches platform metadata, builds JSON
│   ├── review_sssom_metadata.py        # Interactive review workflow & audit attribution recorder
│   ├── write_sssom_file.py             # Orchestrator: performs smart merge & writes canonical SSSOM TSVs
│   ├── sync_mapping_commons_registry.py# Sync utility: ingests official Mapping Commons Registry sets
│   ├── load_from_athena.py             # Loader for OHDSI Athena (OMOP CDM v5) vocabulary archives
│   ├── load_from_graph.py              # Loader for RDF/OWL/Turtle/N-Triples/N3 graphs
│   ├── load_from_sssom.py              # Loader for pre-existing SSSOM TSV files
│   ├── load_from_spreadsheet.py        # Loader for Excel (.xls, .xlsx), CSV, and TSV tables
│   ├── load_from_webpage.py            # Scraper/loader for HTML tables (ROMULUS, W3C, EC JRC)
│   ├── load_from_document.py           # Loader for MARC records, ZIP archives, and DOI/Zenodo resolutions
│   ├── load_from_manual_input.py       # Interactive CLI tool for manual SSSOM mapping entry
│   ├── load_tables_from_document.py    # Table extractor for PDF, DOCX, and scanned documents
│   ├── load_thesaurus_from_document.py # SKOS extractor for PDF thesauri
│   ├── ingest_sssom_archive.py         # Streaming ingester for SSSOM tarball archives (.tgz)
│   ├── retrieve_github_metadata.py     # GitHub REST API metadata & commit contributor scraper
│   └── retrieve_sourceforge_metadata.py# SourceForge API & SVN file history scraper
├── www/                                # Static web application (GitHub Pages deployment)
│   ├── .nojekyll                       # Bypasses Jekyll processing on GitHub Pages
│   ├── index.html                      # Single-page app: Pathfinder, Query Engine, Endpoints, Topology
│   ├── css/
│   │   └── style.css                   # Responsive dark theme UI stylesheet
│   ├── js/
│   │   └── app.js                      # Client-side BFS shortest-path algorithm & mapping query engine
│   └── data/
│       ├── mappings_graph.json         # Graph topology, node metrics, & pre-indexed mapping samples
│       └── endpoints.json              # Complete 325+ vocabulary endpoint registry
└── test/
    ├── __init__.py                     # Test package marker
    ├── test_urls.txt                   # Canonical benchmark URLs across 13 formats
    ├── run_urls_test.py                # End-to-end integration test driver
    └── test_loaders.py                 # Pytest unit test suite (23/23 passing)
```

---

## Supported Formats & Loaders

| Loader Module | Source Types & Extensions | Example Sources |
|---|---|---|
| `load_from_athena.py` | OHDSI Athena (OMOP CDM v5) ZIP archives and directories (`VOCABULARY.csv`, `CONCEPT.csv`, `CONCEPT_RELATIONSHIP.csv`) | Athena vocabulary bundles (SNOMED CT, LOINC, UCUM, OMOP Extension, RxNorm, MeSH, ICD-10) |
| `load_from_graph.py` | Turtle (`.ttl`), RDF/XML (`.rdf`, `.owl`, `.xml`), N-Triples (`.nt`), N3 (`.n3`) | SUMO-DBpedia, BIBO2SPAR, DCAT-PROV, SIO-RO Bridge OWL, Schema.org Turtle, BFO-Mappings PROV-to-BFO with OWL 2 annotated axioms |
| `load_from_sssom.py` | SSSOM TSV (`.sssom.tsv`, `.sssom.tsv.gz`, `.sssom`) | Biomappings `positive.sssom.tsv` |
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

# Create and activate a virtual environment (recommended)
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

Convert any supported mapping source into the `./commons` registry structure with a single command:

```bash
# Process an online Turtle mapping non-interactively
python src/write_sssom_file.py "https://raw.githubusercontent.com/ontologyportal/sumo/master/mappings/DBpediaMapping.ttl" -y --no-edit

# Process an online CSV crosswalk
python src/write_sssom_file.py "https://data.nber.org/gem/icd10cmtoicd9gem.csv" -y --no-edit

# Process a MARC authority mapping file (with MeSH/LCSH cross-referencing and predicate detection)
python src/write_sssom_file.py "https://raw.githubusercontent.com/galterlibrary/mapping-project/master/LCSH-to-MeSH-mapping-data.txt" -y --no-edit

# Process all 20 ROMULUS ontology alignment metadata pages
python src/write_sssom_file.py "https://web.archive.org/web/20180102005419id_/http://www.thezfiles.co.za/ROMULUS/ontologyAlignmentMetadata.html" -y --no-edit

# Ingest an SSSOM tarball archive into the canonical ./commons structure
python src/ingest_sssom_archive.py --archive "path/to/sssom.tgz" --max-files 50
```

All generated files are placed under `./commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv` (or `.sssom.tsv.gz` when `--compress` is passed).

---

## Usage Guide

### Ingesting OHDSI Athena (OMOP CDM) Vocabularies

To extract cross-vocabulary relationships (`Maps to`, `lojban`, `LOINC - SNOMED eq`, `SNOMED -RxNorm eq`, etc.) from an downloaded [OHDSI Athena](https://athena.ohdsi.org/) vocabulary bundle (ZIP archive or extracted directory containing `VOCABULARY.csv`, `CONCEPT.csv`, and `CONCEPT_RELATIONSHIP.csv`):

```bash
# Ingest an Athena export directory or ZIP directly into ./commons
python src/write_sssom_file.py "path/to/athena_export" -y --no-edit --compress
```

### Converting an External Mapping Source

```bash
python src/write_sssom_file.py <URL_OR_FILEPATH> [OPTIONS]
```

#### CLI Options:
- `-y`, `--yes`: Automatically accept metadata review prompts without blocking.
- `--no-edit`: Skip opening an interactive text editor to edit the metadata JSON.
- `--compress`: Write canonical outputs in gzip-compressed `.sssom.tsv.gz` format.
- `-o <PATH>`, `--output <PATH>`: Write an additional copy of the merged output to the specified file path.

### Automated Pipeline Execution

For continuous integration (CI) or batch scripts, combine `-y` and `--no-edit`:

```bash
python src/write_sssom_file.py https://example.org/mappings.ttl -y --no-edit
```

### Interactive Review Workflow

When run without `-y`, `write_sssom_file.py` displays the extracted SSSOM metadata and prompts for confirmation:
1. Review the generated CURIE prefix map, license, and dataset provenance details.
2. Optionally open your `$EDITOR` (or Notepad / `vi`) to modify any metadata field.
3. Supply reviewer attribution (`reviewer_id`) to be recorded in the audit trail.
4. Merge rows into the canonical `./commons` file with automatic deduplication.

### Manual SSSOM Entry

To manually curate mapping triples through an interactive terminal prompt:

```bash
python src/load_from_manual_input.py -o manual.sssom.tsv
```

### Synchronizing from the Mapping Commons Registry

`src/sync_mapping_commons_registry.py` queries the live Mapping Commons specifications catalog at [https://mapping-commons.github.io/data/mapping-specifications.json](https://mapping-commons.github.io/data/mapping-specifications.json), downloads published SSSOM mapping files, and harmonizes them into `./commons`:

```bash
# 1. List all registered initiatives and available SSSOM mapping files
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

**Key synchronization features**:
- Automatically groups and merges multi-file initiatives between the same ontologies into a single cumulative canonical file (e.g., multiple MP-to-HP files merge into `commons/mp/hp/mp_hp.sssom.tsv`).
- Populates every row with self-contained provenance, structure release versions, and curator attribution.
- Dynamically filters the `# curie_map:` in each target file to include only the prefixes referenced by the mapped entities.

---

## Test Suite & Validation

The test suite validates individual loaders, date derivation rules, compression handling, and end-to-end conversions across 13 mapping formats.

### 1. Run Unit Tests (Pytest)

```bash
pytest test/test_loaders.py -v
```

### 2. Run Comprehensive URL Test Suite

```bash
python test/run_urls_test.py
```

The driver executes all benchmark URLs in `test/test_urls.txt`, checks exit codes, generates SSSOM files, and writes a detailed report to `test/tmp-sssom-run-<timestamp>/report.json`:

```text
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

Validate any file in `./commons` using the official `sssom` Python package:

```bash
python -c "import sssom.parsers; mdf = sssom.parsers.parse_sssom_table('commons/dbo/sumo/dbo_sumo.sssom.tsv'); print('Valid! Rows:', len(mdf.df))"
```

---

## Contributing Mappings via Pull Requests

Contributions are welcome! Whether you are adding new crosswalks, refining existing predicates, updating provenance metadata, or deprecating false positives, please submit a Pull Request to [https://github.com/Superraptor/KOS-Mappings/](https://github.com/Superraptor/KOS-Mappings/).

### Core Repository Principles

1. **Single Cumulative Totality**: Each file `commons/<subject_prefix>/<object_prefix>/<subject_prefix>_<object_prefix>.sssom.tsv` is the single canonical source of truth for **all** mappings between those two vocabularies.
2. **Self-Contained Row Provenance**: Because rows in a file may originate from multiple tools, dates, or contributors over time, **each row must be self-contained**, carrying its own `mapping_justification`, source/target versions, `mapping_tool`, authentic `mapping_date`, and curator attribution (`author_id` / `creator_id`).
3. **Filtered CURIE Maps**: SSSOM YAML headers must define only the prefixes referenced in that file.

---

### Adding New Mappings

#### Method A: Automated Ingestion via Pipeline (Recommended for Datasets)
If you have an external alignment file, ontology, spreadsheet, archive, or URL, run the ingestion CLI:

```bash
# 1. Ingest an external URL or local file (smart-merges directly into ./commons)
python src/write_sssom_file.py "https://example.org/new_mappings.ttl" -y --no-edit

# 2. Or run interactive mode to preview and adjust metadata before writing:
python src/write_sssom_file.py "path/to/my_mappings.xlsx"
```

After adding new files in `./commons`, rebuild the web index so the GitHub Pages explorer includes your additions:

```bash
python src/build_web_index.py
```

#### Method B: Direct Row Addition
If you are curating a small number of mappings by hand:
1. Locate (or create) the target file at `commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv`.
2. Append new rows following the tab-separated column structure.
3. Ensure all mandatory fields are populated:
   - `subject_id`: Source CURIE (e.g., `mondo:0005015`)
   - `predicate_id`: Standard SKOS/OWL predicate (`skos:exactMatch`, `skos:closeMatch`, `skos:broadMatch`, `skos:narrowMatch`, `owl:equivalentClass`, `rdfs:subClassOf`)
   - `object_id`: Target CURIE (e.g., `doid:10652`)
   - `mapping_justification`: Single SEMAPV CURIE (e.g., `semapv:ManualMappingCuration`, `semapv:LexicalMatching`)
   - `author_id` / `creator_id`: Curator ORCID (`orcid:0000-...`) or email (`mailto:...`)
   - `mapping_date`: Authentic curation date formatted as `YYYY-MM-DD`
   - `license`: Canonical license identifier or URL (e.g., `CC0-1.0`, `CC-BY-4.0`)
4. Verify that any newly introduced prefixes are declared in the `# curie_map:` header.

#### Method C: Interactive CLI Curation
```bash
python src/load_from_manual_input.py -o manual.sssom.tsv
python src/write_sssom_file.py manual.sssom.tsv -y --no-edit
```

---

### Modifying Existing Mappings

1. **Locate the Row**: Open `commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv` and locate the row by `(subject_id, predicate_id, object_id)`.
2. **Refine Predicates**:
   - Upgrade `skos:closeMatch` to `skos:exactMatch` when concepts are verified to be conceptually equivalent.
   - Use `skos:broadMatch` (subject is narrower than object) or `skos:narrowMatch` (subject is broader than object) for hierarchical alignments.
3. **Upgrade Justification**:
   - When human review verifies an automated match, update `mapping_justification` to `semapv:ManualMappingCuration` (must be a single SEMAPV CURIE).
4. **Add Commentary & Attribution**:
   - Record rationale in `comment` and append your ORCID to `author_id` or `reviewer_id` (pipe-delimited `|` for multiple curators).

---

### Removing or Deprecating Mappings

- **Complete Deletion**: Remove invalid or erroneous rows directly from the `.sssom.tsv` file.
- **Negative / Disjoint Assertions**: To explicitly record that two concepts are disjoint (preventing automated tools from re-asserting a false match), retain the row and set:
  - `predicate_id`: `owl:disjointWith`
  - `mapping_justification`: `semapv:ManualMappingCuration`
  - `comment`: `Mappable: No. Incompatible domain semantics verified.`

---

### Pre-Submission Validation

Before opening a pull request, run the test suite locally:

```bash
# 1. Run unit tests
pytest test/test_loaders.py -v

# 2. Validate modified SSSOM TSV file with sssom-py
python -c "import sssom.parsers; mdf = sssom.parsers.parse_sssom_table('commons/<p1>/<p2>/<p1>_<p2>.sssom.tsv'); print('Validated! Rows:', len(mdf.df))"

# 3. Rebuild the web explorer index
python src/build_web_index.py
```

---

### Pull Request Checklist

1. **Branch**: Create a feature branch off `main` (e.g., `git checkout -b feat/add-rxnorm-mappings`).
2. **Commit Message**: Use a clear, descriptive commit title (e.g., `feat(commons): add RxNorm to SNOMED crosswalks`).
3. **PR Description**: Summarize the affected vocabularies, row changes, and upstream authority references.
4. **Automated Checks**: Verify `pytest test/test_loaders.py -v` passes and GitHub Actions workflows succeed.

---

## Registry Submission Guidelines

To register mappings from this repository in the [Mapping Commons Registry](https://mapping-commons.github.io/):

1. **Verify SSSOM Conformance**: Ensure target files under `./commons` validate cleanly with `sssom validate`.
2. **Persistent Identifier**: Each mapping set carries a canonical `mapping_set_id` (`https://w3id.org/commons/mappings/<p1>_<p2>`).
3. **Register Mapping Repository**: Add the raw GitHub URLs to the Mapping Commons `mapping-server.yml` configuration:
   ```yaml
   - id: kos-mappings-dbo-sumo
     name: DBpedia to SUMO Mappings
     url: https://raw.githubusercontent.com/Superraptor/KOS-Mappings/main/commons/dbo/sumo/dbo_sumo.sssom.tsv
     license: CC0-1.0
   ```
4. **Submit Pull Request**: Open a pull request against [mapping-commons/mapping-commons.github.io](https://github.com/mapping-commons/mapping-commons.github.io).

---

## License & Constituent Provenance

The software and pipeline code in this repository are distributed under the [MIT License](https://opensource.org/licenses/MIT).

### Constituent License Inheritance

KOS-Mappings preserves upstream intellectual property and licensing rights for all ingested mappings:
- **No Blanket Assumptions**: Mappings do not default to CC0 1.0. Every constituent mapping set and row inherits the license explicitly declared by its upstream authority, ontology graph, document, or repository API.
- **Inherited Upstream Licenses**:
  - **Public Domain Mark 1.0**: CMS / CDC General Equivalence Mappings (GEM)
  - **CC-BY 4.0**: European Commission JRC Crosswalks (DataCite to DCAT-AP, DCAT-AP to Schema.org), SIO-RO Bridge
  - **CC-BY 2.5**: BIBO2SPAR
  - **CC-BY-SA 3.0**: Schema.org
  - **W3C Software and Document Notice**: W3C DCAT-PROV, W3C PROV-DC
  - **CC0 1.0**: BFO-Mappings PROV-to-BFO, OBO Relations Ontology, Basic Formal Ontology, Biomappings
  - **Terms of Use**: EBSCO QRH title lists, OHDSI Athena constituent vocabularies
  - **Unspecified**: Where an upstream source does not provide an explicit machine-readable license, the license is recorded as `https://w3id.org/sssom/license/unspecified` rather than assuming a permissive license.
