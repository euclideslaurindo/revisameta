# Backup/restore tooling: Postgres client, rclone (S3 copy and off-site upload), GnuPG (encryption).
FROM alpine:3.24.4
RUN apk add --no-cache bash coreutils tar curl gnupg rclone postgresql16-client \
    && adduser -D -u 10001 backup
COPY backup.sh restore.sh common.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh
USER backup
WORKDIR /backups
ENTRYPOINT ["/usr/local/bin/backup.sh"]
