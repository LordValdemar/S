#!/usr/bin/env bash
# Instala o Painel de Propagandas como serviço (Linux / Raspberry Pi OS).
# Uso:  sudo ./deploy/instalar-linux.sh
set -euo pipefail

PASTA="$(cd "$(dirname "$0")/.." && pwd)"
USUARIO="${SUDO_USER:-$(whoami)}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Rode com sudo: sudo $0" >&2
  exit 1
fi

echo "==> Pasta do programa: $PASTA"
echo "==> Usuário do serviço: $USUARIO"

if [ ! -x "$PASTA/.venv/bin/python" ]; then
  echo "==> Criando ambiente virtual"
  sudo -u "$USUARIO" python3 -m venv "$PASTA/.venv"
fi
echo "==> Instalando dependências"
sudo -u "$USUARIO" "$PASTA/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$USUARIO" "$PASTA/.venv/bin/pip" install --quiet -r "$PASTA/requirements.txt"
sudo -u "$USUARIO" mkdir -p "$PASTA/dados"

echo "==> Instalando o serviço"
sed -e "s#__PASTA__#$PASTA#g" -e "s#__USUARIO__#$USUARIO#g" \
  "$PASTA/deploy/painel-propagandas.service" > /etc/systemd/system/painel-propagandas.service
systemctl daemon-reload
systemctl enable --now painel-propagandas

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "Pronto! O painel inicia sozinho quando o computador ligar."
echo "  Painel:   http://${IP:-localhost}:5000/"
echo "  Exibição: http://${IP:-localhost}:5000/player"
echo
echo "Comandos úteis:"
echo "  systemctl status painel-propagandas     # ver se está rodando"
echo "  journalctl -u painel-propagandas -f     # acompanhar os logs"
echo "  sudo systemctl restart painel-propagandas"
