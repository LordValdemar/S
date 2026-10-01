#!/usr/bin/env bash
# Atualiza o Painel de Propagandas para a versão mais nova do repositório.
# Faz um backup antes e confere se o sistema voltou no ar.
#
#   sudo /opt/painel-propagandas/deploy/vps/atualizar.sh
set -euo pipefail

PASTA="$(cd "$(dirname "$0")/../.." && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Rode com sudo: sudo $0" >&2; exit 1; }
cd "$PASTA"

echo "==> Backup antes de atualizar"
"$PASTA/deploy/vps/gerenciar.sh" backup < /dev/null

echo "==> Baixando a versão nova"
ANTES="$(git rev-parse --short HEAD)"
git pull --ff-only
DEPOIS="$(git rev-parse --short HEAD)"
if [ "$ANTES" = "$DEPOIS" ]; then
  echo "Já está na versão mais nova ($DEPOIS)."
  exit 0
fi
git log --oneline "$ANTES..$DEPOIS"
chown -R root:root "$PASTA" && chown -R painel:painel "$PASTA/dados"

echo "==> Atualizando as dependências"
"$PASTA/.venv/bin/pip" install --quiet -r requirements.txt

echo "==> Reiniciando (o banco de dados é atualizado sozinho na inicialização)"
systemctl restart painel-propagandas
for _ in $(seq 1 30); do
  if curl -fsS --noproxy "*" --max-time 2 http://127.0.0.1:5000/saude >/dev/null 2>&1; then
    echo "OK: atualizado de $ANTES para $DEPOIS e funcionando."
    exit 0
  fi
  sleep 1
done

cat >&2 <<ERRO
ERRO: o painel não voltou depois da atualização.
  Veja o motivo:      journalctl -u painel-propagandas -n 80
  Voltar o código:    sudo git -C $PASTA checkout $ANTES && sudo systemctl restart painel-propagandas
  Se o banco foi alterado, restaure o backup feito agora há pouco
  (o mais recente em $PASTA/dados/backups) com:
    sudo systemctl stop painel-propagandas
    sudo $PASTA/deploy/vps/gerenciar.sh restaurar $PASTA/dados/backups/<arquivo>.zip
    sudo systemctl start painel-propagandas
ERRO
exit 1
