#!/bin/sh
set -e
mkdir -p /data
if [ "$(id -u)" = "0" ]; then
  chown -R appuser:appuser /data
  exec runuser -u appuser -- "$@"
fi
exec "$@"
