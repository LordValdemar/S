#!/usr/bin/env bash
# Roda o gerenciar.py com o mesmo usuário e a mesma configuração do serviço.
#
#   sudo /opt/painel-propagandas/deploy/vps/gerenciar.sh listar-empresas
#   sudo /opt/painel-propagandas/deploy/vps/gerenciar.sh trocar-senha dono
#   sudo /opt/painel-propagandas/deploy/vps/gerenciar.sh backup
set -euo pipefail

PASTA="$(cd "$(dirname "$0")/../.." && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Rode com sudo: sudo $0 $*" >&2; exit 1; }

# --pty quando há um terminal (comandos que pedem senha); --pipe em scripts.
if [ -t 0 ]; then MODO=--pty; else MODO=--pipe; fi

exec systemd-run --quiet --wait --collect "$MODO" \
  -p User=painel -p Group=painel \
  -p EnvironmentFile=/etc/painel-propagandas/ambiente \
  -p WorkingDirectory="$PASTA" \
  "$PASTA/.venv/bin/python" "$PASTA/gerenciar.py" "$@"
