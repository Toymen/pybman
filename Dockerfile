FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md COPYING ./
COPY pybman ./pybman
COPY webapp ./webapp

RUN pip install --no-cache-dir .[web]

ENV DB_PATH=/data/pubman.db \
    PORT=8000
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /data \
    && chown -R app:app /app /data
VOLUME ["/data"]
EXPOSE 8000
USER app

# A single worker process is required: the sync loop and its lock live in
# process memory, and multiple gunicorn workers would each run their own
# duplicate background sync against the same SQLite file. --threads gives
# concurrency for request handling within that one process.
CMD ["sh", "-c", "gunicorn -w 1 --threads 4 -b 0.0.0.0:${PORT} webapp.wsgi:app"]
