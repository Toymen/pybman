FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md COPYING ./
COPY pybman ./pybman
COPY webapp ./webapp

RUN pip install --no-cache-dir .[web]

ENV DB_PATH=/data/pubman.db \
    PORT=8000
VOLUME ["/data"]
EXPOSE 8000

CMD ["python", "-m", "webapp.app"]
