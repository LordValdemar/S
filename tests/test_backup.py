import os
import zipfile

import pytest

from conftest import PNG, enviar, postar
from propagandas import backup, db


def test_backup_e_restauracao(logado):
    config = logado.application.config
    enviar(logado, "oferta.png", PNG)
    postar(logado, "/letreiro", {"letreiro": "antes"})
    arquivo = backup.criar_backup(config)

    # Muda tudo depois do backup...
    postar(logado, "/letreiro", {"letreiro": "depois"})
    with logado.application.app_context():
        (pid,) = [linha["id"] for linha in db.obter().execute("SELECT id FROM propagandas")]
    postar(logado, f"/propaganda/{pid}/excluir")
    assert logado.get("/api/playlist").get_json()["itens"] == []

    # ...e restaura.
    guardados = backup.restaurar_backup(config, arquivo)
    playlist = logado.get("/api/playlist").get_json()
    assert playlist["letreiro"] == "antes"
    assert logado.get(playlist["itens"][0]["url"]).data == PNG
    assert os.path.exists(os.path.join(guardados, "banco.sqlite3"))


def test_mantem_so_os_ultimos_backups(app, monkeypatch):
    app.config["BACKUP_MANTER"] = 2
    nomes = iter(["20260101-000000", "20260102-000000", "20260103-000000"])

    class Data:
        @staticmethod
        def now():
            class Agora:
                def __format__(self, _):
                    return next(nomes)
            return Agora()

    monkeypatch.setattr(backup, "datetime", Data)
    for _ in range(3):
        backup.criar_backup(app.config)
    assert sorted(os.listdir(app.config["PASTA_BACKUPS"])) == [
        "backup-20260102-000000.zip", "backup-20260103-000000.zip",
    ]


def test_restaurar_recusa_zip_malicioso(app, tmp_path):
    ruim = tmp_path / "ruim.zip"
    with zipfile.ZipFile(ruim, "w") as z:
        z.writestr("banco.sqlite3", b"")
        z.writestr("midia/../../fora.txt", b"ataque")
    with pytest.raises(ValueError):
        backup.restaurar_backup(app.config, str(ruim))

    outro = tmp_path / "outro.zip"
    with zipfile.ZipFile(outro, "w") as z:
        z.writestr("qualquer.txt", b"")
    with pytest.raises(ValueError, match="não é um backup"):
        backup.restaurar_backup(app.config, str(outro))
