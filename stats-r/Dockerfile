# Statistics service (R + plumber). Multi-arch base image (amd64/arm64).
FROM rocker/r-ver:4.6.2 AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libsodium-dev libcurl4-openssl-dev libssl-dev libxml2-dev \
       libfontconfig1-dev libfreetype6-dev libpng-dev libharfbuzz-dev \
       libfribidi-dev libjpeg-dev libtiff-dev libuv1-dev libwebp-dev \
       curl git \
    && rm -rf /var/lib/apt/lists/*

RUN Rscript -e "install.packages('renv')"

WORKDIR /app

# Restore the exact package versions pinned in renv.lock into the site library.
FROM base AS runtime
COPY renv.lock ./
RUN Rscript -e "renv::restore(lockfile = 'renv.lock', library = .libPaths()[1], prompt = FALSE)"

COPY R/ ./R/
COPY plumber.R entrypoint.R .lintr ./
COPY tests/ ./tests/
COPY fixtures/ ./fixtures/

RUN useradd --system --create-home --uid 10001 stats && chown -R stats /app
USER stats

EXPOSE 8000
CMD ["Rscript", "entrypoint.R"]
