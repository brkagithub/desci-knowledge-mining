import time
import logging
from airflow.models import DagRun, TaskInstance
from airflow.settings import Session


def get_status_of_dag_until_finished(
    session, dag_id, run_id, task_id, xcom_key, poll_interval=10, max_wait_time=300
):
    start_time = time.time()
    dag_run_status = None

    while time.time() - start_time < max_wait_time:
        logging.info(
            f"Polling for DAG run status... elapsed time: {int(time.time() - start_time)} seconds"
        )

        # Refresh session
        session.expire_all()

        dag_run = (
            session.query(DagRun)
            .filter(DagRun.dag_id == dag_id, DagRun.run_id == run_id)
            .first()
        )

        if dag_run:
            logging.info(f"DAG run state: {dag_run.state}")
        else:
            logging.info("DAG run not found yet.")

        if dag_run and dag_run.state in ["success", "failed"]:
            dag_run_status = dag_run.state
            break

        time.sleep(poll_interval)

    if dag_run_status == "success":
        logging.info("DAG run completed successfully. Fetching XCom value...")
        task_instance = (
            session.query(TaskInstance)
            .filter(
                TaskInstance.dag_id == dag_id,
                TaskInstance.run_id == run_id,
                TaskInstance.task_id == task_id,
            )
            .first()
        )

        if task_instance:
            xcom_value = task_instance.xcom_pull(task_ids=task_id, key=xcom_key)
            return {"status": "success", "xcom_value": xcom_value}

    elif dag_run_status == "failed":
        logging.error("DAG run failed.")
        return {"status": "failed"}

    logging.error("DAG did not complete in the expected time.")
    return {"status": "timeout"}


def get_status_of_dag(session, dag_id, run_id, task_id=None, xcom_key=None):
    # Refresh session
    session.expire_all()

    # Fetch the DAG run
    dag_run = (
        session.query(DagRun)
        .filter(DagRun.dag_id == dag_id, DagRun.run_id == run_id)
        .first()
    )

    if not dag_run:
        logging.info("DAG run not found.")
        return {"status": "not_found"}

    logging.info(f"DAG run state: {dag_run.state}")

    # If task_id is provided, check if the task is still running
    if dag_run.state == "running":
        # Fetch the currently running task instance
        running_task_instance = (
            session.query(TaskInstance)
            .filter(
                TaskInstance.dag_id == dag_id,
                TaskInstance.run_id == run_id,
                TaskInstance.state == "running"
            )
            .first()
        )
        if running_task_instance:
            # Fetch the 'progress' XCom value from the running task
            progress_value = running_task_instance.xcom_pull(task_ids=running_task_instance.task_id, key="progress")
            
            # Construct the response to include the 'progress' XCom value
            response = {
                "status": "running",
                "current_task_id": running_task_instance.task_id,
                "progress": progress_value
            }
            
            return response
    
    # If task_id and xcom_key are provided, fetch the XCom value
    if dag_run.state == "success" and task_id and xcom_key:
        task_instance = (
            session.query(TaskInstance)
            .filter(
                TaskInstance.dag_id == dag_id,
                TaskInstance.run_id == run_id,
                TaskInstance.task_id == task_id,
            )
            .first()
        )

        if task_instance:
            response = {"status": dag_run.state}

            if xcom_key:
                xcom_value = task_instance.xcom_pull(task_ids=task_id, key=xcom_key)
                response["xcom_value"] = xcom_value

            suggested_question = task_instance.xcom_pull(
                task_ids=task_id, key="suggested_questions"
            )
            if suggested_question:
                response["suggested_questions"] = suggested_question

            return response

    return {"status": dag_run.state}
