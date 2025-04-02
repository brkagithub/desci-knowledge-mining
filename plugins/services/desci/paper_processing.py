import json
from plugins.utils.desci.llm_prompts import (
    get_prompt_basic_info,
    get_prompt_citations,
    get_prompt_go_subgraph,
    get_prompt_doid_subgraph,
    get_prompt_chebi_subgraph,
    get_prompt_atc_subgraph,
    get_prompt_spar_ontology,
    get_prompt_spar_citations,
    get_prompt_section_page_numbers,
    get_prompt_go_ontology,
    get_prompt_suggested_questions,
)
from plugins.services.anthropic_client import generate_response
from plugins.services.desci.biology_api import (
    update_go_terms,
    update_doid_terms,
    update_chebi_terms,
    update_atc_terms,
)
from plugins.utils.regex import extract_bracket_content, is_empty_array
import re
import logging
from plugins.services.anthropic_client import get_client

CITATIONS_OFFSET = 6


def extract_sections(client, paper_array):
    original_labels = [
        "Abstract",
        "Introduction",
        "Methods",
        "Materials and methods",
        "Material and methods",
        "Results",
        "Discussion",
    ]
    # Convert labels to lowercase for case-insensitive matching
    labels = [label.lower() for label in original_labels]
    label_page_numbers = {label: [] for label in labels}
    label_mapping = {label.lower(): label for label in original_labels}

    # Find appearances of each label
    for element in paper_array:
        page_number = element["metadata"]["page_number"]
        text = element["text"].lower()  # Convert text to lowercase
        for label in labels:
            if label in text:
                # Skip table of contents for other labels than Introduction
                if page_number == 1 and (label != labels[0] and label != labels[1]):
                    continue
                label_page_numbers[label].append(page_number)

    # Mark Methods as either of the 4 found labels
    methods_labels = [
        "materials and methods",
        "material and methods",
    ]
    if len(label_page_numbers["methods"]) == 0:
        for method_label in methods_labels:
            if len(label_page_numbers[method_label]) > 0:
                label_page_numbers["methods"] = label_page_numbers[method_label]
                break

    # Remove unneeded labels
    for method_label in methods_labels:
        if method_label in label_page_numbers:
            label_page_numbers.pop(method_label, None)
            labels.remove(method_label)
        original_labels.remove(label_mapping[method_label])
    first_appearance = {
        label: (pages[0] if pages else None)
        for label, pages in label_page_numbers.items()
    }

    # Remove those which are not found
    first_appearance = {
        label: page for label, page in first_appearance.items() if page is not None
    }

    sorted_labels = sorted(
        first_appearance.items(),
        key=lambda x: x[1] if x[1] is not None else float("inf"),
    )

    label_page_ranges = {}

    for i in range(len(sorted_labels)):
        label, start_page = sorted_labels[i]
        if start_page is None:
            continue
        if i == 0:
            start_page = 1  # Ensure the first label starts from page 1
        if i == len(sorted_labels) - 1:
            # Last label goes until the end
            end_page = paper_array[-1]["metadata"]["page_number"]
        elif i + 1 < len(sorted_labels):
            next_start_page = sorted_labels[i + 1][1]
            end_page = (
                next_start_page
                if next_start_page is not None and next_start_page >= start_page
                else start_page
            )
        else:
            end_page = None
        label_page_ranges[label] = (start_page, end_page)

    labels_with_no_range = [
        label_mapping[label] for label in labels if label not in label_page_ranges
    ]

    additional_label_page_ranges = {}

    # Maybe shouldn't have this in if and just do it anyways
    if labels_with_no_range:
        prompt = get_prompt_section_page_numbers(paper_array, labels_with_no_range)
        answer = generate_response(client, prompt, max_tokens=4096)

        answer_lines = answer.split("\n")
        for line in answer_lines:
            match = re.match(r"(\w+),\s*(\d+),\s*(\d+)", line.strip())
            if match:
                label = match.group(1).lower()
                start_page = int(match.group(2))
                end_page = int(match.group(3))
                additional_label_page_ranges[label] = (start_page, end_page)

    # Merge the additional label ranges into the total label ranges
    for label, (start_page, end_page) in additional_label_page_ranges.items():
        label_page_ranges[label] = (start_page, end_page)

    extracted_labels = [
        label_mapping.get(label)
        for label in label_page_ranges.keys()
        if label_mapping.get(label) is not None
    ]
    skipped_labels = [
        label for label in original_labels if label not in extracted_labels
    ]

    if skipped_labels:
        logging.info(f"Skipped sections: {', '.join(skipped_labels)}")
    else:
        logging.info("All sections were extracted.", label_page_ranges)

    # Make sure introduction starts from page 0
    if "introduction" in label_page_ranges:
        start_page, end_page = label_page_ranges["introduction"]
        label_page_ranges["introduction"] = (0, end_page)

    # Return the combined label ranges
    return label_page_ranges


def get_generated_basic_info_text(client, paper_dict):
    spar_array = list(set(paper_dict["introduction"] + paper_dict["abstract"]))

    try:
        prompt_basic_info = get_prompt_basic_info(spar_array)
        generated_basic_info_text = generate_response(client, prompt_basic_info)
        logging.info("Generated basic text from Claude:", generated_basic_info_text)
    except Exception as e:
        logging.error("Generated basic info text exception")
        logging.error(f"Exception message: {str(e)}")
        generated_basic_info_text = ""

    return generated_basic_info_text


def get_generated_citations(client, paper_dict):
    try:
        prompt_citations = get_prompt_citations(paper_dict["citations"])
        generated_citations = generate_response(
            client, prompt_citations, max_tokens=4096
        )
        logging.info("Generated citations from Claude:", generated_citations)
    except Exception as e:
        logging.error("Generated citations exception")
        logging.error(f"Exception message: {str(e)}")
        generated_citations = ""

    return generated_citations


def get_go_generated_subgraph_text(client, paper_dict):
    try:
        go_array = list(
            set(
                paper_dict["introduction"]
                + paper_dict["methods"]
                + paper_dict["results"]
                + paper_dict["discussion"]
            )
        )
        prompt_subgraph = get_prompt_go_subgraph(go_array)
        generated_subgraph_text = generate_response(
            client, prompt_subgraph, max_tokens=3000
        )
        logging.info("Generated GO subgraph from Claude:", generated_subgraph_text)
        generated_subgraph = json.loads(generated_subgraph_text)
        generated_subgraph = update_go_terms(generated_subgraph, client)
        generated_subgraph_text = str(generated_subgraph)
        logging.info("Generated subgraph using GO API:", generated_subgraph_text)
    except Exception as e:
        logging.error("Generated subgraph exception")
        logging.error(f"Exception message: {str(e)}")
        generated_subgraph = {}
        generated_subgraph_text = str(generated_subgraph)

    return generated_subgraph_text


def get_doid_generated_subgraph_text(client, paper_dict):
    try:
        doid_array = list(
            set(
                paper_dict["introduction"]
                + paper_dict["abstract"]
                + paper_dict["results"]
                + paper_dict["discussion"]
            )
        )
        prompt_subgraph = get_prompt_doid_subgraph(doid_array)
        generated_subgraph_text = generate_response(
            client, prompt_subgraph, max_tokens=3000
        )
        logging.info("Generated DOID subgraph from Claude:", generated_subgraph_text)
        generated_subgraph = json.loads(generated_subgraph_text)
        generated_subgraph = update_doid_terms(generated_subgraph, client)
        generated_subgraph_text = json.dumps(generated_subgraph)
        logging.info("Generated subgraph using DOID API:", generated_subgraph_text)
    except Exception as e:
        logging.error("Generated subgraph exception")
        logging.error(f"Exception message: {str(e)}")
        generated_subgraph = {}
        generated_subgraph_text = json.dumps(generated_subgraph)

    return generated_subgraph_text


def get_chebi_generated_subgraph_text(client, paper_dict):
    try:
        chebi_array = list(
            set(
                paper_dict["introduction"]
                + paper_dict["abstract"]
                + paper_dict["results"]
                + paper_dict["discussion"]
            )
        )
        prompt_subgraph = get_prompt_chebi_subgraph(chebi_array)
        generated_subgraph_text = generate_response(
            client, prompt_subgraph, max_tokens=3000
        )
        logging.info("Generated ChEBI subgraph from Claude:", generated_subgraph_text)
        generated_subgraph = json.loads(generated_subgraph_text)
        generated_subgraph = update_chebi_terms(generated_subgraph, client)
        generated_subgraph_text = json.dumps(generated_subgraph)
        logging.info("Generated subgraph using CHEBI API:", generated_subgraph_text)
    except Exception as e:
        logging.error("Generated subgraph exception")
        logging.error(f"Exception message: {str(e)}")
        generated_subgraph = {}
        generated_subgraph_text = json.dumps(generated_subgraph)

    return generated_subgraph_text


def get_atc_generated_subgraph_text(client, paper_dict):
    try:
        atc_array = list(
            set(
                paper_dict["introduction"]
                + paper_dict["abstract"]
                + paper_dict["results"]
                + paper_dict["discussion"]
            )
        )
        prompt_subgraph = get_prompt_atc_subgraph(atc_array)
        generated_subgraph_text = generate_response(
            client, prompt_subgraph, max_tokens=3000
        )
        logging.info("Generated ATC subgraph from Claude:", generated_subgraph_text)
        generated_subgraph = json.loads(generated_subgraph_text)
        generated_subgraph = update_atc_terms(generated_subgraph, client)
        generated_subgraph_text = json.dumps(generated_subgraph)
        logging.info("Generated subgraph using ATC API:", generated_subgraph_text)
    except Exception as e:
        logging.error("Generated subgraph exception")
        logging.error(f"Exception message: {str(e)}")
        generated_subgraph = {}
        generated_subgraph_text = json.dumps(generated_subgraph)

    return generated_subgraph_text


import concurrent.futures


def process_paper(client, paper_dict):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit each task to the executor
        future_basic_info = executor.submit(
            get_generated_basic_info_text, client, paper_dict
        )
        future_citations = executor.submit(get_generated_citations, client, paper_dict)
        future_go_subgraph = executor.submit(
            get_go_generated_subgraph_text, client, paper_dict
        )
        future_doid_subgraph = executor.submit(
            get_doid_generated_subgraph_text, client, paper_dict
        )
        future_chebi_subgraph = executor.submit(
            get_chebi_generated_subgraph_text, client, paper_dict
        )
        future_atc_subgraph = executor.submit(
            get_atc_generated_subgraph_text, client, paper_dict
        )

        # Retrieve results as they complete
        generated_basic_info = future_basic_info.result()
        generated_citations = future_citations.result()
        generated_go_subgraph = future_go_subgraph.result()
        generated_doid_subgraph = future_doid_subgraph.result()
        generated_chebi_subgraph = future_chebi_subgraph.result()
        generated_atc_subgraph = future_atc_subgraph.result()

    return (
        generated_basic_info,
        generated_citations,
        generated_go_subgraph,
        generated_doid_subgraph,
        generated_chebi_subgraph,
        generated_atc_subgraph,
    )


def fix_json_string_manually(json_string):
    # Find the last occurrence of '},' and trim the string after it
    last_brace_index = json_string.rfind("},")

    # If '},' is found, cut off the string after it
    if last_brace_index != -1:
        json_string = json_string[
            : last_brace_index + 1
        ]  # Include the closing brace '}'

    # Remove any trailing commas after the last valid JSON object
    if json_string.endswith(","):
        json_string = json_string[:-1]

    # Close the JSON array
    json_string += "]"

    return json_string


def get_subgraph_citations(client, citations_text):
    prompt_spar_citations = get_prompt_spar_citations(citations_text)
    generated_citations_spar_text = generate_response(
        client, prompt_spar_citations, max_tokens=4096
    )
    logging.info("Generated SPAR citations from Claude:", generated_citations_spar_text)
    try:
        generated_citation_spar = json.loads(generated_citations_spar_text)
    except:
        fixed_citations = fix_json_string_manually(generated_citations_spar_text)

        logging.info(f"Fixed citations: {fixed_citations}")

        generated_citation_spar = json.loads(fixed_citations)

        # Also possible to do with LLM, but manually seems to be working better even though it has some edge cases where it might not work
        # prompt = get_prompt_convert_to_json(generated_citations_spar_text)

        # generated_citations_spar_text = generate_response(
        #     client, prompt, max_tokens=4096
        # )

        # print(f"Fixed citations: {generated_citations_spar_text}")

        # generated_citation_spar = json.loads(generated_citations_spar_text)

    return generated_citation_spar


def get_subgraph_basic_info(client, basic_info_text):
    if is_empty_array(basic_info_text):
        return basic_info_text

    prompt_spar_ontology = get_prompt_spar_ontology(basic_info_text)
    generated_graph_text = generate_response(
        client, prompt_spar_ontology, max_tokens=4096
    )
    logging.info("Generated SPAR graph from Claude:", generated_graph_text)

    generated_graph_text = generated_graph_text.strip()

    if generated_graph_text.startswith("```json") and generated_graph_text.endswith(
        "```"
    ):
        generated_graph_text = generated_graph_text[7:-3].strip()

    return generated_graph_text


def get_subgraph_go(client, generated_go_subgraph):
    try:
        if is_empty_array(generated_go_subgraph):
            return []
        prompt_go_ontology = get_prompt_go_ontology(generated_go_subgraph)
        generated_graph_text = generate_response(
            client, prompt_go_ontology, max_tokens=2000
        )
        logging.info("Generated GO subgraph from Claude:", generated_graph_text)
        extracted_content = extract_bracket_content(generated_graph_text)
        return json.loads(extracted_content)
    except Exception as e:
        logging.error("Error generating GO subgraph")
        logging.error(f"Exception message: {str(e)}")
        return []


def get_subgraph_doid(generated_doid_subgraph):
    try:
        generated_doid_subgraph = json.loads(generated_doid_subgraph)
        rdf_doid_subgraph = [
            {
                "@id": f"http://purl.obolibrary.org/obo/{item['disease_id']}",
                "dcterms:title": item["disease"],
                "dcterms:description": item["findings"],
            }
            for item in generated_doid_subgraph
        ]
        return rdf_doid_subgraph
    except Exception as e:
        logging.error("Error generating DOID subgraph")
        logging.error(f"Exception message: {str(e)}")
        return []


def get_subgraph_chebi(generated_chebi_subgraph):
    try:
        generated_chebi_subgraph = json.loads(generated_chebi_subgraph)
        rdf_chebi_subgraph = [
            {
                "@id": f"http://purl.obolibrary.org/obo/{item['compound_id']}",
                "dcterms:title": item["compound"],
                "dcterms:description": item["findings"],
            }
            for item in generated_chebi_subgraph
        ]
        return rdf_chebi_subgraph
    except Exception as e:
        logging.error("Error generating CHEBI subgraph")
        logging.error(f"Exception message: {str(e)}")
        return []


def get_subgraph_atc(generated_atc_subgraph):
    try:
        generated_atc_subgraph = json.loads(generated_atc_subgraph)
        rdf_atc_subgraph = [
            {
                "@id": f"http://purl.bioontology.org/ontology/ATC/{item['drug_id']}",
                "dcterms:title": item["drug"],
                "dcterms:description": item["findings"],
            }
            for item in generated_atc_subgraph
        ]
        return rdf_atc_subgraph
    except Exception as e:
        logging.error("Error generating ATC subgraph")
        logging.error(f"Exception message: {str(e)}")
        return []


def create_graph(client, basic_info_text, citations_text, subgraph):
    generated_go_subgraph = subgraph["go"]
    generated_doid_subgraph = subgraph["doid"]
    generated_chebi_subgraph = subgraph["chebi"]
    generated_atc_subgraph = subgraph["atc"]

    generated_graph = {}

    try:
        generated_graph_text = get_subgraph_basic_info(client, basic_info_text)
        generated_graph = json.loads(generated_graph_text)
    except Exception as e:
        logging.error("Generating graph exception")
        logging.error(f"Exception message: {str(e)}")

    generated_graph["obi:OBI_0000299"] = []

    generated_graph["obi:OBI_0000299"] += get_subgraph_go(
        client, generated_go_subgraph=generated_go_subgraph
    )
    generated_graph["obi:OBI_0000299"] += get_subgraph_doid(generated_doid_subgraph)
    generated_graph["obi:OBI_0000299"] += get_subgraph_chebi(generated_chebi_subgraph)
    generated_graph["obi:OBI_0000299"] += get_subgraph_atc(generated_atc_subgraph)

    try:
        generated_graph["cito:cites"] = get_subgraph_citations(client, citations_text)
    except Exception as e:
        logging.error("Error generating citations")
        logging.error(f"Exception message: {str(e)}")

    if (
        generated_graph.get("dcterms:identifier")
        and generated_graph.get("dcterms:identifier")
        != "https://doi.org/XX.XXXX/XX.XXXX"
    ):
        generated_graph["@id"] = generated_graph["dcterms:identifier"]
    else:
        generated_graph["@id"] = "PLEASE FILL IN THE DOI URL IDENTIFIER HERE"

    return generated_graph


def create_section_arrays(paper_array, section_ranges):
    introduction_array = []
    abstract_array = []
    methods_array = []
    results_array = []
    discussion_array = []

    for element in paper_array:
        page_number = element["metadata"]["page_number"]
        text = element["text"]
        if (
            "introduction" in section_ranges
            and section_ranges["introduction"][0]
            <= page_number
            <= section_ranges["introduction"][1]
        ):
            introduction_array.append(text)
        if (
            "abstract" in section_ranges
            and section_ranges["abstract"][0]
            <= page_number
            <= section_ranges["abstract"][1]
        ):
            abstract_array.append(text)
        if (
            "methods" in section_ranges
            and section_ranges["methods"][0]
            <= page_number
            <= section_ranges["methods"][1]
        ):
            methods_array.append(text)
        if (
            "results" in section_ranges
            and section_ranges["results"][0]
            <= page_number
            <= section_ranges["results"][1]
        ):
            results_array.append(text)
        if (
            "discussion" in section_ranges
            and section_ranges["discussion"][0]
            <= page_number
            <= section_ranges["discussion"][1]
        ):
            discussion_array.append(text)

    return {
        "introduction": introduction_array,
        "abstract": abstract_array,
        "methods": methods_array,
        "results": results_array,
        "discussion": discussion_array,
    }


def process_json_array(paper_array, client):
    section_ranges = extract_sections(client, paper_array)
    paper_array_dict = create_section_arrays(paper_array, section_ranges)

    num_of_pages = paper_array[-1]["metadata"]["page_number"]
    paper_array_dict["citations"] = [
        element["text"]
        for element in paper_array
        if "text" in element
        and element["metadata"]["page_number"] >= num_of_pages - CITATIONS_OFFSET
    ]

    return paper_array_dict


def get_suggested_questions(paper_dict):
    try:
        client = get_client()

        prompt_questions = get_prompt_suggested_questions(paper_dict)

        generated_questions_text = generate_response(
            client, prompt_questions, max_tokens=3000
        )

        questions_array = generated_questions_text.strip().split("\n")

        questions_array = [question for question in questions_array if question.strip()]

        logging.info("Generated suggested questions from Claude:", questions_array)

    except Exception as e:
        logging.error("Error generating questions")
        logging.error(f"Exception message: {str(e)}")
        questions_array = []

    return questions_array
