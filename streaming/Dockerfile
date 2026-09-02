FROM python:3.12-slim

WORKDIR /app

COPY streaming/requirements.txt ./streaming/requirements.txt
RUN pip install --no-cache-dir -r streaming/requirements.txt

COPY pipeline ./pipeline
COPY streaming ./streaming

CMD ["python", "-m", "streaming.producer"]
