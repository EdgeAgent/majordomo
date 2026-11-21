FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir ".[documents]"

# All state (memory, sessions, schedules, workspace) lives here.
ENV MAJORDOMO_DATA_DIR=/data \
    MAJORDOMO_HOST=0.0.0.0 \
    MAJORDOMO_PORT=8080
VOLUME ["/data"]
EXPOSE 8080

CMD ["majordomo", "serve"]
