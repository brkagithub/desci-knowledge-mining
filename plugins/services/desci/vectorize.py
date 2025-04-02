import json
from plugins.utils.desci.llm_prompts import get_prompt_vectorization_summary
from plugins.services.anthropic_client import generate_response
from plugins.services.zilliz import find_similar_title
import logging


def get_summary(client, graph):
    """Generate a summary for the provided graph using the given client."""
    try:
        prompt_vectorization_summary = get_prompt_vectorization_summary(graph)
        summary = generate_response(client, prompt_vectorization_summary)
        logging.info("Generated graph summary from Claude:", summary)
    except Exception as e:
        logging.error("Generated graph summary exception")
        logging.error(f"Exception message: {str(e)}")
        summary = ""

    return summary


def get_vectorization_params(client, graph):
    summary = get_summary(client, graph)
    return {"summary": summary, "title": graph["dcterms:title"], "doi": graph["@id"]}


def get_final_citations(citations):
    updated_citations = []

    for citation in citations:
        if citation["@id"] == "":
            similar_citation = find_similar_title(citation["dcterms:title"])
            # Threshhold
            if similar_citation[1] > 0.9:
                citation["@id"] = similar_citation[0].metadata["doi"]

        updated_citations.append(citation)

    return updated_citations
