import logging
from airflow import DAG
from airflow.operators.python import PythonOperator
import json
import os
import sys
from datetime import datetime, timedelta
from io import BytesIO


sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
from plugins.services.desci.ka_service import json_arr_to_ka
from plugins.services.unstructured_service import unstructured_convert_pdf_to_json_array
from plugins.services.desci.paper_processing import get_suggested_questions
from plugins.utils.db import Session, LogEntry

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2023, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def extract_parameters(**kwargs):
    ti = kwargs["ti"]
    ti.xcom_push(key="progress", value="Extracting parameters")
    selected_llm = kwargs["dag_run"].conf.get("selectedLLM")
    file_format = kwargs["dag_run"].conf.get("fileFormat")
    file = kwargs["dag_run"].conf.get("file")
    file_name = kwargs["dag_run"].conf.get("fileName")

    params = {
        "selected_llm": selected_llm,
        "file_format": file_format,
        "file": file,
        "file_name": file_name,
    }
    # Store start time in XCom
    ti.xcom_push(key="start_time", value=datetime.utcnow())

    # Store file path in XCom for later use

    file_size = file.getbuffer().nbytes if file else 0
    ti.xcom_push(key="file_size", value=file_size)

    ti.xcom_push(key="params", value=params)


def convert_pdf_to_json_array(**kwargs):
    ti = kwargs["ti"]
    ti.xcom_push(key="progress", value="Processing PDF")
    params = ti.xcom_pull(key="params", task_ids="extract_parameters")
    file = params["file"]
    file_format = params["file_format"].lower()
    file_name = params["file_name"]
    selected_llm = params["selected_llm"]

    logging.info(f"File pulled from xcom: {file}")
    logging.info(f"File format: {file_format}")
    logging.info(f"File name: {file_name}")
    
    
    if file_format != "pdf":
        logging.error("File format is not PDF")
        return

    try:
        logging.info("Calling unstructured convert function")
        unstr_json_array = unstructured_convert_pdf_to_json_array(file, file_name)
        logging.info(
            f"Successfully converted PDF to JSON array with length {len(unstr_json_array)}"
        )
        params = {
            "selected_llm": selected_llm,
            "unstr_json_array": unstr_json_array,
            "file_name": file_name,
            "selected_llm": selected_llm,
        }
        ti.xcom_push(key="params", value=params)
    except Exception as e:
        error_message = f"Failed to parse PDF using Unstructured: {str(e)}"
        logging.error(error_message, exc_info=True)
        log_error_to_db(filename=file_name, error_message=error_message, error_flag=1)

        return "Failed to parse PDF using Unstructured"


def convert_to_ka(**kwargs):
    ti = kwargs["ti"]
    ti.xcom_push(key="progress", value="Starting Knowledge Asset creation process")
    params = ti.xcom_pull(key="params", task_ids="convert_pdf_to_json_array")
    file_name = params["file_name"]
    selected_llm = params["selected_llm"]
    unstr_json_array = params["unstr_json_array"]

    start_time = ti.xcom_pull(key="start_time", task_ids="extract_parameters")
    file_size = ti.xcom_pull(key="file_size", task_ids="extract_parameters")

    try:
        ka = json_arr_to_ka(unstr_json_array, ti)
        logging.info(f"Got JSON LD KA from PDF {json.dumps(ka)}")

        # Calculate response time
        end_time = datetime.utcnow()
        response_time = (end_time - start_time).total_seconds()

        session = Session()
        log_entry = LogEntry(
            filename=file_name,
            file_size=file_size,
            response_time=response_time,
            ka_json_ld=json.dumps(ka),
        )
        session.add(log_entry)
        session.commit()
        session.close()

        ti.xcom_push(key="ka", value=ka)

        suggested_questions = get_suggested_questions(paper_dict=ka)
        ti.xcom_push(key="suggested_questions", value=suggested_questions)

    except Exception as e:
        error_message = f"Failed to convert chunks to JSON LD: {str(e)}"
        logging.error(error_message, exc_info=True)
        log_error_to_db(filename=file_name, error_message=error_message, error_flag=1)

        return "Failed to convert chunks to JSON LD"


def log_error_to_db(filename, error_message, error_flag):
    try:
        session = Session()
        log_entry = LogEntry(
            filename=filename, error_message=error_message, error_flag=error_flag
        )
        session.add(log_entry)
        session.commit()
        session.close()
    except Exception as e:
        logging.error(f"Failed to log error to database: {str(e)}", exc_info=True)


with DAG(
    "desci_pdf_to_jsonld",
    default_args=default_args,
    description="Process parameters for PDF to JSON-LD conversion using DeSci pipeline",
    schedule_interval=None,
    catchup=False,
) as dag:

    extract_parameters_task = PythonOperator(
        task_id="extract_parameters",
        provide_context=True,
        python_callable=extract_parameters,
        dag=dag,
    )

    convert_pdf_to_json_array_task = PythonOperator(
        task_id="convert_pdf_to_json_array",
        provide_context=True,
        python_callable=convert_pdf_to_json_array,
        dag=dag,
    )

    convert_to_ka = PythonOperator(
        task_id="convert_to_ka",
        provide_context=True,
        python_callable=convert_to_ka,
        dag=dag,
    )

    (extract_parameters_task >> convert_pdf_to_json_array_task >> convert_to_ka)

logging.info("DAG desci_pdf_to_jsonld loaded")
