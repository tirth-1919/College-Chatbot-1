# Backup and restore

The PostgreSQL dump does not contain S3-compatible media objects. Enable bucket versioning or provider backups, and include the bucket in the same retention and restore drills. The database stores media object keys and content hashes; restore a matching object-store snapshot before re-enabling media links.

Compose starts a daily `pg_dump -Fc` backup worker and retains 14 days in `./backups`. Treat this local volume as a convenience only; production backups need encryption, off-site replication, access controls and restore drills.

To restore into a clean Compose database, stop the API and worker, then run `docker compose exec -T db pg_restore -U chatbot -d chatbot --clean --if-exists < backup.dump`. Confirm migrations and application health before reopening traffic. Never test restores over the only live database.
