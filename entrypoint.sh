#!/bin/sh
# Snapshot the container's env so cron jobs (which run with a stripped env)
# can source it before invoking python.
set -e
env | sed 's/^\([^=]*\)=\(.*\)$/export \1="\2"/' > /container.env
chmod 600 /container.env
exec "$@"
