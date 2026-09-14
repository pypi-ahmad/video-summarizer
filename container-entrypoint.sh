#!/bin/sh
# Container bootstrap entrypoint for Docker and Hugging Face Spaces.
# Responsible for preparing persistent storage directory structure and symlinking
# app state (runs, OAuth credentials, logs) to the volume mount before startup.
# Must not execute application logic directly; delegates by execing container arguments.
# Next: Dockerfile (which configures this entrypoint) or app.py (the main application).
set -eu

# Persistent volume boundary: Hugging Face Spaces mount persistent NVMe storage at /data.
# VIDEO_SUMMARIZER_DATA_DIR allows overriding the mount path in custom container environments.
data_root="${VIDEO_SUMMARIZER_DATA_DIR:-/data}"

# Persistence symlink boundary: redirects app working directories and Adversal CLI's
# default credential directory (~/.adversal) to the persistent mount so OAuth logins,
# completed jobs, and logs survive container restarts.
mkdir -p "$data_root/runs" "$data_root/adversal" "$data_root/logs"
ln -sfnT "$data_root/runs" /home/user/app/runs
ln -sfnT "$data_root/adversal" /home/user/.adversal
ln -sfnT "$data_root/logs" /home/user/app/logs

exec "$@"
