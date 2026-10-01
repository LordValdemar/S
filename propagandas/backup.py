"""Backup e restauração (banco + arquivos de mídia) em um único .zip."""

import glob
import logging
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime

log = logging.getLogger("propagandas.backup")

NOME_BANCO_NO_ZIP = "banco.sqlite3"
PASTA_MIDIA_NO_ZIP = "midia/"


def criar_backup(config):
    """Gera dados/backups/backup-AAAAMMDD-HHMMSS.zip e apaga os mais antigos."""
    pasta_backups = config["PASTA_BACKUPS"]
    os.makedirs(pasta_backups, exist_ok=True)
    destino = os.path.join(pasta_backups, f"backup-{datetime.now():%Y%m%d-%H%M%S}.zip")
    parcial = destino + ".parcial"

    with tempfile.TemporaryDirectory() as temporaria:
        # A API de backup do SQLite copia o banco com segurança mesmo em uso.
        copia = os.path.join(temporaria, NOME_BANCO_NO_ZIP)
        origem = sqlite3.connect(config["BANCO"])
        alvo = sqlite3.connect(copia)
        try:
            origem.backup(alvo)
        finally:
            alvo.close()
            origem.close()

        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as arquivo_zip:
            arquivo_zip.write(copia, NOME_BANCO_NO_ZIP)
            for caminho in sorted(glob.glob(os.path.join(config["PASTA_MIDIA"], "*"))):
                if os.path.isfile(caminho):
                    # Imagens e vídeos já são comprimidos: guardar sem recomprimir.
                    arquivo_zip.write(
                        caminho,
                        PASTA_MIDIA_NO_ZIP + os.path.basename(caminho),
                        compress_type=zipfile.ZIP_STORED,
                    )
    os.replace(parcial, destino)

    antigos = sorted(glob.glob(os.path.join(pasta_backups, "backup-*.zip")))
    for velho in antigos[: max(0, len(antigos) - config["BACKUP_MANTER"])]:
        os.remove(velho)

    log.info("Backup criado: %s", destino)
    return destino


def _validar_zip(arquivo_zip):
    nomes = arquivo_zip.namelist()
    if NOME_BANCO_NO_ZIP not in nomes:
        raise ValueError("Este arquivo não é um backup do Painel de Propagandas.")
    for nome in nomes:
        if nome == NOME_BANCO_NO_ZIP or nome == PASTA_MIDIA_NO_ZIP:
            continue
        resto = nome[len(PASTA_MIDIA_NO_ZIP):]
        # Bloqueia caminhos maliciosos como "../../etc/passwd".
        if not nome.startswith(PASTA_MIDIA_NO_ZIP) or not resto or "/" in resto or "\\" in resto or resto.startswith("."):
            raise ValueError(f"Backup com conteúdo inesperado: {nome}")


def restaurar_backup(config, caminho_zip):
    """Substitui banco e mídia pelo conteúdo do backup.

    Os dados atuais são movidos para dados/antes-da-restauracao-<data>/,
    para nada ser perdido. Pare o servidor antes de restaurar.
    """
    with zipfile.ZipFile(caminho_zip) as arquivo_zip:
        _validar_zip(arquivo_zip)

        guardados = os.path.join(config["PASTA_DADOS"], f"antes-da-restauracao-{datetime.now():%Y%m%d-%H%M%S}")
        os.makedirs(guardados)
        for sufixo in ("", "-wal", "-shm"):
            if os.path.exists(config["BANCO"] + sufixo):
                shutil.move(config["BANCO"] + sufixo, guardados)
        if os.path.exists(config["PASTA_MIDIA"]):
            shutil.move(config["PASTA_MIDIA"], os.path.join(guardados, "midia"))
        os.makedirs(config["PASTA_MIDIA"])

        for nome in arquivo_zip.namelist():
            if nome == PASTA_MIDIA_NO_ZIP:
                continue
            destino = (
                config["BANCO"] if nome == NOME_BANCO_NO_ZIP
                else os.path.join(config["PASTA_MIDIA"], nome[len(PASTA_MIDIA_NO_ZIP):])
            )
            with arquivo_zip.open(nome) as origem, open(destino, "wb") as saida:
                shutil.copyfileobj(origem, saida)

    log.info("Backup restaurado de %s (dados anteriores em %s)", caminho_zip, guardados)
    return guardados


def fez_backup_hoje(config):
    hoje = f"backup-{datetime.now():%Y%m%d}-"
    return any(
        os.path.basename(c).startswith(hoje)
        for c in glob.glob(os.path.join(config["PASTA_BACKUPS"], "backup-*.zip"))
    )
