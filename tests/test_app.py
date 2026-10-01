import importlib
import io
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("PASTA_MIDIA", str(tmp_path / "midia"))
    monkeypatch.setenv("ARQUIVO_DADOS", str(tmp_path / "playlist.json"))
    monkeypatch.delenv("SENHA_ADMIN", raising=False)
    import app as modulo
    modulo = importlib.reload(modulo)
    modulo.app.config["TESTING"] = True
    with modulo.app.test_client() as c:
        c.modulo = modulo
        yield c


def enviar(cliente, nome, duracao=7):
    return cliente.post(
        "/enviar",
        data={"duracao": str(duracao), "arquivos": (io.BytesIO(b"conteudo"), nome)},
        content_type="multipart/form-data",
    )


def test_envio_aparece_na_playlist(cliente):
    enviar(cliente, "promo.jpg")
    enviar(cliente, "video.mp4")
    enviar(cliente, "virus.exe")  # extensão não permitida é ignorada

    itens = cliente.get("/api/playlist").get_json()["itens"]
    assert [i["tipo"] for i in itens] == ["imagem", "video"]
    assert itens[0]["duracao"] == 7
    assert cliente.get(itens[0]["url"]).data == b"conteudo"


def test_editar_mover_e_excluir(cliente):
    enviar(cliente, "a.png")
    enviar(cliente, "b.png")
    dados = cliente.modulo.carregar_dados()
    a, b = dados["itens"]

    cliente.post(f"/item/{b['id']}/mover/cima")
    ordem = [i["nome"] for i in cliente.modulo.carregar_dados()["itens"]]
    assert ordem == ["b.png", "a.png"]

    # Desmarcar "ativo" tira o item do ar
    cliente.post(f"/item/{a['id']}/atualizar", data={"nome": "A", "duracao": "5"})
    itens = cliente.get("/api/playlist").get_json()["itens"]
    assert [i["id"] for i in itens] == [b["id"]]

    cliente.post(f"/item/{b['id']}/excluir")
    assert not os.path.exists(os.path.join(cliente.modulo.PASTA_MIDIA, b["arquivo"]))
    assert cliente.get("/api/playlist").get_json()["itens"] == []


def test_periodo_de_validade(cliente):
    esta_no_ar = cliente.modulo.esta_no_ar
    hoje = date(2026, 10, 1)
    assert esta_no_ar({"ativo": True, "inicio": "2026-09-01", "fim": "2026-10-31"}, hoje)
    assert not esta_no_ar({"ativo": True, "inicio": "2026-10-02", "fim": ""}, hoje)
    assert not esta_no_ar({"ativo": True, "inicio": "", "fim": "2026-09-30"}, hoje)


def test_letreiro(cliente):
    cliente.post("/letreiro", data={"letreiro": "Pão quentinho às 17h!"})
    assert cliente.get("/api/playlist").get_json()["letreiro"] == "Pão quentinho às 17h!"


def test_senha_protege_painel_mas_nao_a_exibicao(cliente):
    cliente.modulo.SENHA_ADMIN = "1234"
    assert cliente.get("/").status_code == 401
    assert cliente.get("/player").status_code == 200
    assert cliente.get("/api/playlist").status_code == 200
    autorizado = cliente.get("/", headers={"Authorization": "Basic OjEyMzQ="})  # ":1234"
    assert autorizado.status_code == 200
