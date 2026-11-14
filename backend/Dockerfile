# Backend image: Python (FastAPI) + R with the packages the analyses need + the Analyse-Together R functions.
# Nobody has to install R or run pip on their own machine. Build context: ./backend (see docker-compose.yml).
FROM python:3.11-slim-bookworm

# R from Debian, with the two packages r/analysis.R uses (as Debian packages: no compiling). git is only used to
# clone Analyse-Together and to record its commit in the audit trail.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git r-base-core r-cran-dplyr r-cran-jsonlite \
    && rm -rf /var/lib/apt/lists/*

# The validated R functions, sourced at runtime (GPL-3, never copied into this repository). The default branch is
# cloned when the image is built; the commit it ended up on is shown in every response (`versions` audit step).
# To use another branch or commit: docker compose build --build-arg ANALYSE_TOGETHER_REF=<ref>
ARG ANALYSE_TOGETHER_REPO=https://github.com/rivm-syso/Analyse-Together.git
ARG ANALYSE_TOGETHER_REF=
RUN git clone "$ANALYSE_TOGETHER_REPO" /opt/Analyse-Together \
    && if [ -n "$ANALYSE_TOGETHER_REF" ]; then git -C /opt/Analyse-Together checkout "$ANALYSE_TOGETHER_REF"; fi

# Editable install: the app finds config/ and r/ next to its source. [chat] adds LangChain for /chat.
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY config ./config
COPY r ./r
RUN pip install --no-cache-dir -e ".[chat]"

# The data folder is a volume filled by the data-init service (docker-compose.yml).
ENV HL_ANALYSE_TOGETHER_DIR=/opt/Analyse-Together \
    HL_DATA_DIR=/data/HackathonHollandseLuchten/data
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/guidelines', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
