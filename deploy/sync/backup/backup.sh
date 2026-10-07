#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
    exec borg "$@"
fi

# 仅在仓库目录不存在时初始化，损坏或认证失败时保留原数据并退出。
if [ ! -e "$BORG_REPO" ]; then
    borg init --encryption=repokey-blake2
fi

borg create --stats --compression zstd,3 \
    --exclude /deployment/data \
    --exclude /deployment/s3-data \
    --exclude /deployment/borg \
    --exclude /deployment/borg-cache \
    --exclude /deployment/restore \
    --exclude /deployment/.backup.lock \
    "::siyuan-{now:%Y-%m-%dT%H:%M:%S.%f}" /data /s3-data /deployment

# 只有完整创建成功后才按保留策略清理旧归档。
borg prune --list --glob-archives 'siyuan-*' --keep-daily 7 --keep-weekly 4 --keep-monthly 12
borg compact
