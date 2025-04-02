# ka-mining-api

** Activate venv **

```sh
python3 -m venv venv
source venv/bin/activate
```

** Pip install **

```sh
pip install -r requirements.txt
```

** Generate default airflow config **

```sh
airflow config list --defaults
```

paste into ~/airflow/airflow.cfg file

Change the following lines in the config:

```sh
dags_folder = path_to_ka_mining_api/ka-mining-api/dags
parallelism = 32
max_active_tasks_per_dag = 16
max_active_runs_per_dag = 16
enable_xcom_pickling = True
```

**Airflow db init**

```sh
airflow db init

airflow users  create --role Admin --username admin --email admin --firstname admin --lastname admin --password admin
```

**Start airflow server**

```sh
airflow webserver --port 8080 (port where you can open the dashboard)
```

```sh
airflow scheduler (to pick up new DAGs/jobs)
```

**Start Flask server**

```sh
python app.py
```

**SQL db creation**

```sh
CREATE DATABASE ka-mining-api-logging CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
```

** Make sure the DAGs you want to run are unpaused **
Either via UI or

```sh
airflow dags unpause <dag_id>
```

**Trigger the mining DAG via POST request**

<!-- ```sh
    curl -X POST http://localhost:5000/trigger_mining_chatdkg \
     -F "file=@test_jsons/construction_test.json" \
     -F "selectedLLM=gpt-4o-mini" \
     -F "fileFormat=json" \
     -F "keepOntology=false" \
     -F "category=Construction"
```

```sh
    curl -X POST http://localhost:5000/trigger_mining_chatdkg \
     -F "file=@test_jsons/FOAF_test.json" \
     -F "selectedLLM=gpt-4o-mini" \
     -F "fileFormat=json" \
     -F "keepOntology=false" \
     -F "category=Social Media"
``` -->

```sh
    curl -X POST http://localhost:5000/trigger_pipeline \
    -F "file=@test_pdfs/science_paper.pdf" \
    -F "pipelineId=desci_pdf_to_jsonld" \
    -F "fileFormat=pdf" \
    -b "connect.sid=s%3AjLYArFLH7IadiB4dkEDrppgEEQJEqNss.35WzNEW3PySPRIxrDpL5tsRZ%2F%2B%2FNo%2BnZgRPDoRz0y7g; Path=/; HttpOnly;"
```

**Trigger the vectorization DAG via POST request**

```sh
curl -X POST http://localhost:5000/trigger_pipeline \
     -F "file=@test_jsonlds/vectorize_desci.json" \
     -F "pipelineId=vectorize_ka" \
     -F "use_case=desci" \
     -b "connect.sid=s%3AjLYArFLH7IadiB4dkEDrppgEEQJEqNss.35WzNEW3PySPRIxrDpL5tsRZ%2F%2B%2FNo%2BnZgRPDoRz0y7g; Path=/; HttpOnly;"
```

```sh
curl -X GET "http://localhost:5000/check-pipeline-status?pipeline_id=vectorize_ka&run_id=manual__2024-08-16T10:58:29.520303" \
-b "connect.sid=s%3A0RtRtgNy-l4PtQy1j6d8slVEUDCg_U2S.RpjIRxU5gXJxmHtTQwJ1EwaTGIvi5eaT3KFsYtOrDOU; Path=/; HttpOnly;"
```
