import os
from plugins.services.hf_service import embeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

milvus_username = os.getenv("MILVUS_USERNAME")
milvus_password = os.getenv("MILVUS_PASSWORD")
milvus_uri = os.getenv("MILVUS_URI")
environment = os.getenv("PYTHON_ENV")

collection_summary = (
    "DesciSummary" if environment == "PRODUCTION" else "DesciSummaryStaging"
)
collection_title = "DesciTitle" if environment == "PRODUCTION" else "DesciTitleStaging"

vector_db_summaries = Milvus(
    collection_name=collection_summary,
    embedding_function=embeddings,
    connection_args={
        "uri": milvus_uri,
        "user": milvus_username,
        "password": milvus_password,
        "secure": True,
    },
    vector_field="langchain_vector",
    text_field="langchain_text",
    auto_id=True,
)

vector_db_title = Milvus(
    collection_name=collection_title,
    embedding_function=embeddings,
    connection_args={
        "uri": milvus_uri,
        "user": milvus_username,
        "password": milvus_password,
        "secure": True,
    },
    vector_field="langchain_vector",
    text_field="langchain_text",
    auto_id=True,
)


def find_similar_title(title):
    docs = vector_db_title.similarity_search_with_score(title, k=1)
    return docs


# def upload_titles(docs):
#     documents = [
#         Document(page_content=doc["page_content"], metadata=doc["metadata"])
#         for doc in docs
#     ]
#     vector_db_title.add_documents(documents)


# def upload_summaries(docs):
#     documents = [
#         Document(page_content=doc["page_content"], metadata=doc["metadata"])
#         for doc in docs
#     ]
#     vector_db_summaries.add_documents(documents)
