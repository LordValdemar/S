#!/usr/bin/env bash
# Copia os backups diários para fora do servidor com o rclone
# (Google Drive, Backblaze B2, Amazon S3, Dropbox...). Veja docs/HOSPEDAGEM.md, passo 7.
#
#   sudo /opt/painel-propagandas/deploy/vps/backup-externo.sh cofre:painel-backups
#
# Use um remoto CRIPTOGRAFADO (rclone crypt): o backup contém o banco inteiro.
set -euo pipefail

DESTINO="${1:-}"
DIAS="${2:-30}"   # quantos dias de backups manter no destino
PASTA="$(cd "$(dirname "$0")/../.." && pwd)"

[ -n "$DESTINO" ] || { echo "Uso: $0 REMOTO:PASTA [DIAS]  (ex.: $0 cofre:painel-backups 30)" >&2; exit 1; }
command -v rclone >/dev/null || { echo "Instale o rclone: sudo apt install rclone" >&2; exit 1; }

rclone copy "$PASTA/dados/backups" "$DESTINO" --include "backup-*.zip" --log-level NOTICE
rclone delete "$DESTINO" --include "backup-*.zip" --min-age "${DIAS}d" --log-level NOTICE
echo "$(date '+%Y-%m-%d %H:%M') backups copiados para $DESTINO"
