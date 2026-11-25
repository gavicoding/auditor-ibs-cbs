# API local do auditor-ibs-cbs. Uso:
#   docker build -t auditor-ibs-cbs .
#   docker run --rm -p 127.0.0.1:8080:8080 auditor-ibs-cbs
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 auditor
WORKDIR /app
COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY src ./src
RUN pip install --no-cache-dir . && rm -rf /root/.cache
USER auditor
EXPOSE 8080
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/saude')" || exit 1
CMD ["auditor-ibs-cbs", "servir", "--host", "0.0.0.0", "--porta", "8080"]
