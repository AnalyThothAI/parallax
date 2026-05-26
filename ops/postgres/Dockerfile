FROM postgres:18-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        pgbadger \
        powa-web \
        postgresql-18-hypopg \
        postgresql-18-pg-qualstats \
        postgresql-18-pg-stat-kcache \
        postgresql-18-pg-track-settings \
        postgresql-18-pg-wait-sampling \
        postgresql-18-powa \
    && rm -rf /var/lib/apt/lists/*
