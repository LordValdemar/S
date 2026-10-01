import os
from conftest import JPEG, MP4, PNG, enviar, postar

from propagandas import db


def itens_no_ar(cliente):
    return cliente.get("/api/playlist").get_json()["itens"]


def ids(cliente):
    with cliente.application.app_context():
        return [linha["id"] for linha in db.obter().execute("SELECT id FROM propagandas ORDER BY posicao")]


def test_envio_aparece_na_playlist(logado):
    enviar(logado, "promo.jpg", JPEG)
    enviar(logado, "video.mp4", MP4)
    itens = itens_no_ar(logado)
    assert [i["tipo"] for i in itens] == ["imagem", "video"]
    assert itens[0]["duracao"] == 7
    midia = logado.get(itens[0]["url"])
    assert midia.data == JPEG
    assert "immutable" in midia.headers["Cache-Control"]


def test_arquivo_disfarcado_e_recusado(logado):
    resposta = enviar(logado, "virus.jpg", b"MZ\x90\x00 executavel do windows" + b"\x00" * 40)
    assert resposta.status_code == 302
    enviar(logado, "imagem.mp4", PNG)       # extensão não bate com o conteúdo
    enviar(logado, "script.html", b"<script>alert(1)</script>")
    assert itens_no_ar(logado) == []
    assert os.listdir(logado.application.config["PASTA_MIDIA"]) == []


def test_nome_do_arquivo_nao_vira_caminho(logado):
    enviar(logado, "../../../etc/passwd.png", PNG)
    arquivos = os.listdir(logado.application.config["PASTA_MIDIA"])
    assert len(arquivos) == 1 and arquivos[0].endswith(".png") and ".." not in arquivos[0]


def test_editar_mover_e_excluir(logado):
    enviar(logado, "a.png", PNG)
    enviar(logado, "b.png", PNG)
    a, b = ids(logado)

    postar(logado, f"/propaganda/{b}/mover/cima")
    assert ids(logado) == [b, a]

    # Desmarcar "ativo" tira do ar
    postar(logado, f"/propaganda/{a}/atualizar", {"nome": "A", "duracao": "5", "dias": list("0123456")})
    assert [i["id"] for i in itens_no_ar(logado)] == [b]

    arquivo_b = itens_no_ar(logado)[0]["url"].rsplit("/", 1)[-1]
    postar(logado, f"/propaganda/{b}/excluir")
    assert not os.path.exists(os.path.join(logado.application.config["PASTA_MIDIA"], arquivo_b))
    assert ids(logado) == [a]


def test_datas_invalidas(logado):
    enviar(logado, "a.png", PNG)
    (a,) = ids(logado)
    resposta = postar(logado, f"/propaganda/{a}/atualizar",
                      {"nome": "A", "duracao": "5", "ativo": "on", "dias": list("0123456"), "inicio": "2026-10-10", "fim": "2026-10-01"})
    assert "término não pode ser antes" in logado.get(resposta.headers["Location"]).get_data(as_text=True)
    postar(logado, f"/propaganda/{a}/atualizar",
           {"nome": "A", "duracao": "99999", "ativo": "on", "dias": list("0123456"), "inicio": "lixo", "fim": ""})
    with logado.application.app_context():
        linha = db.obter().execute("SELECT * FROM propagandas").fetchone()
    assert linha["inicio"] is None and linha["duracao"] == 3600


def test_letreiro(logado):
    postar(logado, "/letreiro", {"letreiro": "Pão quentinho às 17h!"})
    assert logado.get("/api/playlist").get_json()["letreiro"] == "Pão quentinho às 17h!"
