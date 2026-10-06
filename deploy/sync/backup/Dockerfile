FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends borgbackup ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backup.sh /usr/local/bin/backup
ENTRYPOINT ["/bin/sh", "/usr/local/bin/backup"]
