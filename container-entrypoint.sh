#!/bin/sh
set -eu

data_root="${VIDEO_SUMMARIZER_DATA_DIR:-/data}"

mkdir -p "$data_root/runs" "$data_root/adversal" "$data_root/logs"
ln -sfnT "$data_root/runs" /home/user/app/runs
ln -sfnT "$data_root/adversal" /home/user/.adversal
ln -sfnT "$data_root/logs" /home/user/app/logs

exec "$@"
