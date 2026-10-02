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

command -v python3 >/dev/null || { echo "Instale o Python 3: sudo apt install -y python3" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
  || { echo "É preciso Python 3.10 ou mais novo (use Ubuntu 22.04+, Debian 12+ ou Raspberry Pi OS 12+)." >&2; exit 1; }

# O Ubuntu Server e o Debian não trazem o módulo venv completo (falta o ensurepip).
if ! python3 -c 'import ensurepip, venv' 2>/dev/null; then
  if command -v apt-get >/dev/null; then
    echo "==> Instalando o python3-venv (necessário para o ambiente do Python)"
    apt-get update -q
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-venv
  else
    echo "Instale o módulo venv do Python 3 (pacote python3-venv ou equivalente) e rode de novo." >&2
    exit 1
  fi
fi

# Um ambiente criado pela metade (sem o pip) é apagado e criado de novo.
if [ ! -x "$PASTA/.venv/bin/pip" ]; then
  [ -d "$PASTA/.venv" ] && echo "==> Ambiente virtual incompleto encontrado: recriando" && rm -rf "$PASTA/.venv"
  echo "==> Criando ambiente virtual"
  sudo -u "$USUARIO" python3 -m venv "$PASTA/.venv"
fi
echo "==> Instalando dependências"
sudo -u "$USUARIO" "$PASTA/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$USUARIO" "$PASTA/.venv/bin/pip" install --quiet -r "$PASTA/requirements.txt"
sudo -u "$USUARIO" mkdir -p "$PASTA/dados"

if [ ! -f "$PASTA/configuracao.env" ]; then
  echo "==> Criando o arquivo de configuração (configuracao.env)"
  sudo -u "$USUARIO" cp "$PASTA/configuracao.env.exemplo" "$PASTA/configuracao.env"
fi
# Pode conter chaves (Asaas, e-mail): só o dono lê.
chmod 600 "$PASTA/configuracao.env"

echo "==> Instalando o serviço"
sed -e "s#__PASTA__#$PASTA#g" -e "s#__USUARIO__#$USUARIO#g" \
  "$PASTA/deploy/painel-propagandas.service" > /etc/systemd/system/painel-propagandas.service
systemctl daemon-reload
systemctl enable --now painel-propagandas

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "Pronto! O painel inicia sozinho quando o computador ligar."
echo "  Painel:   http://${IP:-localhost}:5000/"
echo "  Configuração: $PASTA/configuracao.env (depois de editar: sudo systemctl restart painel-propagandas)"
echo
echo "Comandos úteis:"
echo "  systemctl status painel-propagandas     # ver se está rodando"
echo "  journalctl -u painel-propagandas -f     # acompanhar os logs"
echo "  sudo systemctl restart painel-propagandas"
