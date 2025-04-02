import requests
from plugins.services.anthropic_client import generate_response
from plugins.utils.desci.llm_prompts import (
    get_go_api_prompt,
    get_doid_api_prompt,
    get_chebi_api_prompt,
    get_atc_api_prompt,
)
import os
from dotenv import load_dotenv
import re
import concurrent.futures
import logging

dotenv_path = "./.env"
load_dotenv(dotenv_path)
bioontology_api_key = os.getenv("BIONTOLOGY_KEY")


def extract_atc_id(url):
    match = re.search(r"/([^/]+)$", url)
    if match:
        return match.group(1)
    return None


def search_go(term, client, model_identifier="claude-3-haiku-20240307"):
    """Search for a term in the Gene Ontology via QuickGO API."""
    url = "https://www.ebi.ac.uk/QuickGO/services/ontology/go/search"
    params = {"query": term, "limit": 5, "page": 1}
    headers = {"Accept": "application/json"}
    api_response = requests.get(url, headers=headers, params=params)
    go_candidates = api_response.json()["results"][0:4]

    prompt_go_api = get_go_api_prompt(term, go_candidates)

    new_term = ""

    if api_response.status_code == 200:
        try:
            new_term = generate_response(client, prompt_go_api, model_identifier)
            if "GO:" in new_term:
                new_term = new_term.replace("GO:", "GO_")
            logging.info(f"new term: {new_term}, old term: {term}")
            return new_term
        except Exception as e:
            logging.error(f"Error generating response: {e}")
            return "None"
    else:
        logging.info(f"EBI API gave response code {api_response.status_code}")
        return "None"


def search_doid(term, client, model_identifier="claude-3-haiku-20240307"):
    """Search for a term in the DOID Ontology via EBI API."""
    url = "https://www.ebi.ac.uk/ols/api/search"
    params = {
        "q": term,
        "ontology": "doid",
    }
    headers = {"Accept": "application/json"}
    api_response = requests.get(url, headers=headers, params=params)
    doid_candidates = []
    data = api_response.json()
    if data["response"]["numFound"] > 0:
        doid_candidates = [
            {
                "short_form": candidate["short_form"],
                "description": candidate["description"],
                "label": candidate["label"],
            }
            for candidate in data["response"]["docs"][0:4]
        ]

    prompt_doid_api = get_doid_api_prompt(term, doid_candidates)

    new_term = ""

    if api_response.status_code == 200:
        try:
            new_term = generate_response(client, prompt_doid_api, model_identifier)
            if "DOID:" in new_term:
                new_term = new_term.replace("DOID:", "DOID_")
            logging.info(f"new term: {new_term}, old term: {term}")
            return new_term
        except Exception as e:
            logging.error(f"Error generating response: {e}")
            return "None"
    else:
        logging.error(f"EBI API gave response code {api_response.status_code}")
        return "None"


def search_chebi(term, client, model_identifier="claude-3-haiku-20240307"):
    """Search for a term in the ChEBI Ontology via EBI API."""
    url = "https://www.ebi.ac.uk/ols/api/search"
    params = {
        "q": term,
        "ontology": "chebi",
    }
    headers = {"Accept": "application/json"}
    api_response = requests.get(url, headers=headers, params=params)
    chebi_candidates = []
    data = api_response.json()
    if data["response"]["numFound"] > 0:
        chebi_candidates = [
            {
                "short_form": candidate["short_form"],
                "description": candidate["description"],
                "label": candidate["label"],
            }
            for candidate in data["response"]["docs"][0:4]
        ]

    prompt_chebi_api = get_chebi_api_prompt(term, chebi_candidates)

    new_term = ""

    if api_response.status_code == 200:
        try:
            new_term = generate_response(client, prompt_chebi_api, model_identifier)
            if "CHEBI:" in new_term:
                new_term = new_term.replace("CHEBI:", "CHEBI_")
            logging.info(f"new term: {new_term}, old term: {term}")
            return new_term
        except Exception as e:
            logging.error(f"Error generating response: {e}")
            return "None"
    else:
        logging.error(f"EBI API gave response code {api_response.status_code}")
        return "None"


def search_atc(term, client, model_identifier="claude-3-haiku-20240307"):
    """Search for a term in the ATC Ontology via BioOntology API."""
    url = "https://data.bioontology.org/search"
    params = {
        "q": term,
        "ontologies": "ATC",
        "apikey": bioontology_api_key,
    }
    headers = {"Accept": "application/json"}
    api_response = requests.get(url, headers=headers, params=params)
    atc_candidates = []
    data = api_response.json()

    if "collection" in data and len(data["collection"]) > 0:
        candidates = data["collection"]
        atc_candidates = [
            {
                "short_form": extract_atc_id(candidate["@id"]),
                "description": "",
                "label": candidate["prefLabel"],
            }
            for candidate in candidates
        ]

    prompt_atc_api = get_atc_api_prompt(term, atc_candidates)

    new_term = ""

    if api_response.status_code == 200:
        try:
            new_term = generate_response(client, prompt_atc_api, model_identifier)
            logging.info(f"new term: {new_term}, old term: {term}")
            return new_term
        except Exception as e:
            logging.info(f"Error generating response: {e}")
            return "None"
    else:
        logging.error(f"ATC API gave response code {api_response.status_code}")
        return "None"


def update_go_terms(data, client):
    """Update each subject and object in the data array with GO candidates."""
    for entry in data:
        subject_result = search_go(entry["subject"], client)
        entry["subject"] = subject_result
        object_result = search_go(entry["object"], client)
        entry["object"] = object_result

    return [
        entry
        for entry in data
        if entry["subject"] != "None" and entry["object"] != "None"
    ]


def update_doid_terms(data, client):
    """Update each subject and object in the data array with DOID candidates."""
    for entry in data:
        disease_result = search_doid(entry["disease"], client)
        entry["disease_id"] = disease_result

    return [entry for entry in data if entry["disease_id"] != "None"]


def update_chebi_terms(data, client):
    """Update each subject and object in the data array with ChEBI candidates."""
    for entry in data:
        disease_result = search_chebi(entry["compound"], client)
        entry["compound_id"] = disease_result

    return [entry for entry in data if entry["compound_id"] != "None"]


def update_atc_terms(data, client):
    """Update each subject and object in the data array with ATC candidates."""
    for entry in data:
        drug_result = search_atc(entry["drug"], client)
        entry["drug_id"] = drug_result

    return [entry for entry in data if entry["drug_id"] != "None"]
