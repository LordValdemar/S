"""Tarefas em segundo plano: monitorar telas, backup diário e limpeza."""

import logging
import threading
import time
from datetime import timedelta

from . import agenda, alertas, backup, db

log = logging.getLogger("propagandas.tarefas")

INTERVALO = 60          # verifica as telas a cada minuto
INTERVALO_MANUTENCAO = 3600


def limpar_exibicoes_antigas(config):
    limite = agenda.para_texto_utc(agenda.agora_utc() - timedelta(days=config["RETER_EXIBICOES_DIAS"]))
    conexao = db.obter()
    with conexao:
        apagadas = conexao.execute("DELETE FROM exibicoes WHERE exibido_em < ?", (limite,)).rowcount
    if apagadas:
        log.info("%d registro(s) de exibição com mais de %d dias apagados", apagadas, config["RETER_EXIBICOES_DIAS"])


def manutencao(config):
    if config["BACKUP_MANTER"] > 0 and not backup.fez_backup_hoje(config):
        backup.criar_backup(config)
    limpar_exibicoes_antigas(config)


def iniciar_tarefas(app):
    def rodar():
        ultima_manutencao = None
        while True:
            with app.app_context():
                try:
                    alertas.verificar_telas()
                except Exception:
                    log.exception("Falha ao verificar as telas")
                if ultima_manutencao is None or time.monotonic() - ultima_manutencao >= INTERVALO_MANUTENCAO:
                    ultima_manutencao = time.monotonic()
                    try:
                        manutencao(app.config)
                    except Exception:
                        log.exception("Falha na manutenção (backup/limpeza)")
            time.sleep(INTERVALO)

    linha = threading.Thread(target=rodar, name="tarefas", daemon=True)
    linha.start()
    return linha
