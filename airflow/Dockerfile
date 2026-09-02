FROM apache/airflow:3.3.1

COPY airflow/requirements.txt /requirements.txt

RUN pip install --no-cache-dir \
    "apache-airflow==3.3.1" \
    -r /requirements.txt

COPY --chown=airflow:root pipeline /opt/project/pipeline

ENV PYTHONPATH=/opt/project
