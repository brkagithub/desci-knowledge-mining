from plugins.services.anthropic_client import get_client
from plugins.services.desci.paper_processing import (
    process_json_array,
    process_paper,
    create_graph,
)
from plugins.services.desci.vectorize import get_summary, get_final_citations
import logging


def json_arr_to_ka(json_arr, ti):
    client = get_client()

    paper_array_dict = process_json_array(json_arr, client)
    ti.xcom_push(key="progress", value="Splitting into sections")

    (
        generated_basic_info,
        generated_citations,
        generated_go_subgraph,
        generated_doid_subgraph,
        generated_chebi_subgraph,
        generated_atc_subgraph,
    ) = process_paper(client, paper_array_dict)

    ti.xcom_push(key="progress", value="Extracting biological terms")
    generated_graph = create_graph(
        client,
        generated_basic_info,
        generated_citations,
        {
            "go": generated_go_subgraph,
            "doid": generated_doid_subgraph,
            "chebi": generated_chebi_subgraph,
            "atc": generated_atc_subgraph,
        },
    )

    # vector_metadata = get_vectorization_params(client, generated_graph)
    ti.xcom_push(key="progress", value="Forming PDF summary")
    generated_graph["dcterms:hasPart"] = get_summary(client, generated_graph)
    if "cito:cites" in generated_graph and generated_graph["cito:cites"]:
        generated_graph["cito:cites"] = get_final_citations(
            generated_graph["cito:cites"]
        )

    context = generated_graph["@context"]
    if "schema" not in context:
        context["schema"] = "http://schema.org/"
        logging.info(f"Added 'schema' to @context in KA")

    return generated_graph
