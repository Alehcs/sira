FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git make openssl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /usr/local/bin/uv
WORKDIR /sira
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --group evidence --no-install-project
COPY . .
ARG CODE=unknown
ENV SIRA_CODE=${CODE}
RUN uv sync --frozen --group evidence
CMD ["make", "reproduce"]
