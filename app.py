from flask import Flask, request, jsonify, g
from airflow.models import DagBag, DagRun, TaskInstance
from airflow.api.common.experimental.trigger_dag import trigger_dag
from airflow.settings import Session
from datetime import datetime
from datetime import datetime
import logging
import io
import time
from plugins.utils.airflow_utils import get_status_of_dag
import os
from dotenv import load_dotenv
from plugins.utils.auth import COOKIE_NAME, authenticate_token

load_dotenv()
dag_folder = os.getenv("DAG_FOLDER_NAME")
port = os.getenv("PORT")
use_auth = os.getenv("USE_AUTH")
app = Flask(__name__)

dag_bag = DagBag(dag_folder=dag_folder)


def get_user_data():
    if hasattr(g, "user_data"):
        return g.user_data
    else:
        logging.error("User data not found in request context")
        return None


def request_middleware():
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        # Store the session ID in the global object for later use
        logging.info(f"Captured session ID: {session_id}")

        # Authenticate the session ID and store user data in g
        user_data = authenticate_token(session_id)
        if user_data:
            g.user_data = user_data
            logging.info("User data stored in g for the current request.")
        else:
            logging.error("Authentication failed. No user data available.")
    else:
        logging.info("No session ID cookie found")


@app.before_request
def before_request():
    if use_auth:
        request_middleware()
    else:
        pass


# @app.route("/trigger_mining_chatdkg", methods=["POST"])
# def trigger_mining_chatdkg():
#     if "file" not in request.files:
#         return jsonify({"error": "No file part"}), 400

#     file = request.files["file"]
#     if file.filename == "":
#         return jsonify({"error": "No selected file"}), 400

#     file_content = file.read().decode("utf-8")

#     selectedLLM = request.form.get("selectedLLM")
#     fileFormat = request.form.get("fileFormat")
#     keepOntology = request.form.get("keepOntology")
#     category = request.form.get("category")

#     conf = {
#         "file_content": file_content,
#         "selectedLLM": selectedLLM,
#         "fileFormat": fileFormat,
#         "keepOntology": keepOntology,
#         "category": category,
#     }

#     dag_id = "json_to_jsonld"
#     logging.info("Received trigger mining request")

#     if dag_id not in dag_bag.dags:
#         logging.error("DAG not found")
#         return jsonify({"error": "DAG not found"}), 404

#     dag = dag_bag.get_dag(dag_id)
#     run_id = f"manual__{datetime.now().isoformat()}"

#     logging.info("Triggering DAG")
#     trigger_dag(dag_id=dag_id, run_id=run_id, conf=conf)
#     return jsonify({"message": "DAG triggered"}), 200


@app.route("/check-pipeline-status", methods=["GET"])
def check_pipeline_status():
    # pipeline_id = id of pipeline
    # run_id = id of a specific run of a pipeline
    # task_id = id of a subtask of a pipeline
    pipeline_id = request.args.get("pipeline_id")
    run_id = request.args.get("run_id")
    task_id = "vectorize" if "vectorize" in pipeline_id else "convert_to_ka"

    xcom_key = "vectors" if task_id == "vectorize" else "ka"

    if not pipeline_id or not run_id:
        return jsonify({"error": "Missing pipeline_id or run_id"}), 400

    session = Session()
    try:
        result = get_status_of_dag(
            session,
            dag_id=pipeline_id,
            run_id=run_id,
            task_id=task_id,
            xcom_key=xcom_key,
        )

        if result["status"] == "success" and "xcom_value" in result:
            response = {
                "status": result["status"],
                "message": "DAG completed successfully",
                "xcom_value": result["xcom_value"],
            }

            if "suggested_questions" in result:
                response["suggested_questions"] = result["suggested_questions"]

            return jsonify(response), 200
        elif result["status"] == "failed":
            return jsonify({"status": result["status"], "message": "DAG failed"}), 500
        elif result["status"] == "not_found":
            return (
                jsonify({"status": result["status"], "message": "DAG run not found"}),
                404,
            )
        elif result["status"] == "running":
            return (
                jsonify(
                    {
                        "status": result["status"],
                        "message": "DAG is running",
                        "progress": result.get("progress", None),
                    }
                ),
                202,
            )
        else:
            return (
                jsonify(
                    {
                        "status": result["status"],
                        "message": "DAG is in an unknown state",
                    }
                ),
                202,
            )
    finally:
        session.close()


@app.route("/trigger_pipeline", methods=["POST"])
def trigger_pipeline():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    pipeline_id = request.form.get("pipelineId")
    if not pipeline_id:
        return jsonify({"error": "Missing pipelineId"}), 400

    logging.info(f"Received trigger request for pipeline {pipeline_id}")

    if pipeline_id not in dag_bag.dags:
        logging.error("DAG not found")
        return jsonify({"error": "DAG not found"}), 404

    conf = {"fileName": file.filename}
    run_id = f"manual__{datetime.now().isoformat()}"

    if pipeline_id in ["pdf_to_jsonld", "simple_json_to_jsonld", "desci_pdf_to_jsonld"]:
        # in the future store whole config object and send to task
        selected_llm = getattr(g, "user_data", {}).get("model")
        file_format = request.form.get("fileFormat")
        logging.info(f"LLM MODEL: {selected_llm}")
        if not file_format:
            return jsonify({"error": "Missing fileFormat"}), 400

        conf.update({"selectedLLM": selected_llm, "fileFormat": file_format})

        logging.info(f"Reading file and passing content to DAG {pipeline_id}")

        if file_format.lower() == "pdf":
            pdf_file = io.BytesIO(file.read())
            conf["file"] = pdf_file
        elif file_format.lower() == "json":
            file_content = file.read().decode("utf-8")
            conf["file_content"] = file_content
        else:
            return jsonify({"error": "Unsupported file format"}), 400

    elif pipeline_id == "vectorize_ka":
        file_content = file.read().decode("utf-8")
        # later to get with auth service
        embedding_model_name = "guidecare/all-mpnet-base-v2-feature-extraction"
        # in the future store whole config object and send to task
        llm_model_name = getattr(g, "user_data", {}).get("model")
        use_case = request.form.get("use_case")

        if not embedding_model_name:
            return jsonify({"error": "Missing embedding_model_name"}), 400

        if not llm_model_name:
            return jsonify({"error": "Missing llm_model_name"}), 400

        conf.update(
            {
                "knowledge_assets": file_content,
                "embedding_model_name": embedding_model_name,
                "llm_model_name": llm_model_name,
                "use_case": use_case,
            }
        )

    else:
        return jsonify({"error": "Unsupported pipelineId"}), 400

    logging.info(f"Triggering DAG {pipeline_id} with run_id {run_id}")
    dag = dag_bag.get_dag(pipeline_id)
    trigger_dag(dag_id=pipeline_id, run_id=run_id, conf=conf)

    return (
        jsonify(
            {"message": "DAG triggered", "pipeline_id": pipeline_id, "run_id": run_id}
        ),
        200,
    )


if __name__ == "__main__":
    logging.info("Starting Flask app")
    app.run(debug=True, host="0.0.0.0", port=port)
