# Science Paper to JSON-LD Pipeline

This repository contains a pipeline for converting scientific papers (PDFs) into JSON-LD format for ingestion into the OriginTrail Decentralized Knowledge Graph (DKG). The pipeline extracts structured knowledge from papers using NLP and LLMs, with a focus on neuroscience papers.

## Overview

The main pipeline (implemented in `dags/desci_pdf_to_jsonld.py`) performs the following steps:

1. PDF Conversion: Uses unstructured.io to convert PDF papers into JSON format
2. Section Splitting: Breaks the paper into logical sections
3. Metadata Extraction: Extracts paper metadata like title, authors, publication date
4. Reference Extraction: Identifies and structures paper references
5. Knowledge Extraction: Uses LLMs to extract scientific findings related to:
   - Gene Ontology (GO) terms
   - Chemical Entities (ChEBI)
   - Diseases (DOID)
   - Anatomical Therapeutic Chemical Classification (ATC)
6. Summary Generation: Creates paper summaries
7. Vector Storage: Stores embeddings in a vector database for semantic search

## Example Output

See `test_jsonlds/exampl_desci_paper.json` for an example of the structured JSON-LD output format.

## Key Features

- Automated extraction of structured knowledge from scientific papers
- Integration with established biomedical ontologies
- Vector embeddings for semantic search capabilities
- Output in JSON-LD format ready for DKG ingestion

## Usage

The pipeline can be triggered via API endpoints to process scientific papers. The extracted knowledge is structured according to relevant ontologies and prepared for ingestion into the OriginTrail DKG.

See the Airflow documentation in AIRFLOW_README.md for details on running the pipeline.
