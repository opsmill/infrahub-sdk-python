# syntax=docker/dockerfile:1
# Image for Anthropic's OSS Scanner: the SDK checkout at /src with every dependency installed, so the unit tests
# and infrahubctl run without network access. threat_model.md describes how to exercise the SDK.
FROM docker.io/python:3.14.10
ARG UV_VER=0.13.6

ENV PYTHONUNBUFFERED=1 \
    COLUMNS=140 \
    UV_PROJECT_ENVIRONMENT=/src/.venv
ENV PATH="/src/.venv/bin:${PATH}"

RUN pip install --no-cache-dir "uv==${UV_VER}" \
    && git config --global --add safe.directory '*'

# scanner contract: the checkout lives inside the image, at /src
COPY . /src
WORKDIR /src

RUN uv sync --frozen --all-groups --all-extras

# Run the unit tests so a broken image is visible in the build log, without failing the build on a test failure.
RUN uv run pytest -q -p no:cacheprovider tests/unit/ || echo "WARNING: unit tests reported failures"
