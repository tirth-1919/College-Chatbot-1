#!/bin/sh
set -eu
mkdir -p /backups
while true; do
  stamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
  pg_dump --format=custom --no-owner --host=db --username=chatbot chatbot > "/backups/chatbot-${stamp}.dump"
  find /backups -type f -name 'chatbot-*.dump' -mtime +14 -delete
  sleep 86400
done
