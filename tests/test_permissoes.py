"""Permissões do editor (escolhidas pelo administrador) e autorização por QR code."""

import re

from conftest import postar
from propagandas import auth, db, permissoes


def token(cliente):
    with cliente.session_transaction() as sessao:
        sessao.setdefault("csrf", "token-de-teste")
        return sessao["csrf"]


def post(cliente, url, dados=None, **kwargs):
    return cliente.post(url, data={**(dados or {}), "csrf_token": token(cliente)}, **kwargs)


def pessoa(app, usuario, senha="senha-do-editor"):
    cliente = app.test_client()
    post(cliente, "/login", {"usuario": usuario, "senha": senha})
    return cliente


def criar_editor(app, usuario="ana"):
    with app.app_context():
        auth.criar_usuario(db.obter(), 1, usuario, "senha-do-editor", "editor")


def permitir(admin, **niveis):
    return post(admin, "/permissoes", {chave: str(valor) for chave, valor in niveis.items()})


def consultar(app, sql, *parametros):
    with app.app_context():
        return db.obter().execute(sql, parametros).fetchall()


def codigo_do_qr(cliente, funcao, modo="minutos", minutos=5):
    pagina = cliente.get(f"/autorizar?funcao={funcao}&modo={modo}&minutos={minutos}").get_data(as_text=True)
    return re.search(r'class="selo codigo-autorizacao">([A-Z0-9]{8})<', pagina).group(1)


def test_padroes_iguais_ao_sistema_de_antes(logado, app):
    criar_editor(app)
    ana = pessoa(app, "ana")
    assert ana.get("/telas").status_code == 403
    assert ana.get("/relatorios").status_code == 200
    assert "Cadastrar e editar TVs" in logado.get("/permissoes").get_data(as_text=True)


def test_administrador_libera_o_editor_a_cadastrar_tvs(logado, app):
    criar_editor(app)
    ana = pessoa(app, "ana")
    permitir(logado, **{"telas.editor": permissoes.SIM})
    assert "Telas</a>" in ana.get("/").get_data(as_text=True)
    post(ana, "/telas/nova", {"nome": "TV do balcão"})
    assert consultar(app, "SELECT nome FROM telas")[0][0] == "TV do balcão"
    assert ana.get("/usuarios").status_code == 403
    assert "Alertas de tela offline" not in ana.get("/telas").get_data(as_text=True)

    permitir(logado, **{"telas.editor": permissoes.NAO, "conectar_tv.editor": permissoes.NAO, "relatorios.editor": 0})
    assert ana.get("/telas").status_code == 403
    assert ana.get("/relatorios").status_code == 403
    assert "Conectar uma TV" not in ana.get("/").get_data(as_text=True)
    assert permitir(ana, **{"telas.editor": permissoes.SIM}).status_code == 403


def test_editor_cadastra_tv_com_o_qr_do_administrador(logado, app):
    criar_editor(app)
    criar_editor(app, "bia")
    permitir(logado, **{"telas.editor": permissoes.AUTORIZACAO, "relatorios.editor": permissoes.AUTORIZACAO})
    with app.app_context():
        assert permissoes.nivel_do_papel(1, "relatorios", "editor") == permissoes.SIM  # não aceita "com autorização"
    ana, bia = pessoa(app, "ana"), pessoa(app, "bia")
    resposta = ana.get("/telas")
    assert resposta.status_code == 403 and "Precisa de autorização" in resposta.get_data(as_text=True)
    assert "Autorizar</a>" in logado.get("/").get_data(as_text=True)

    codigo = codigo_do_qr(logado, "telas")
    assert ana.get(f"/autorizacao/{codigo}").headers["Location"].endswith("/telas")
    post(ana, "/telas/nova", {"nome": "TV nova"})
    assert consultar(app, "SELECT nome FROM telas")[0][0] == "TV nova"
    assert consultar(app, "SELECT usado_por FROM autorizacoes")[0][0] is not None

    bia.get(f"/autorizacao/{codigo}")                       # o mesmo QR não serve de novo
    assert bia.get("/telas").status_code == 403
    with app.app_context():
        conexao = db.obter()
        with conexao:
            conexao.execute("UPDATE autorizacoes SET ate = '2020-01-01 00:00:00' WHERE usado_por IS NOT NULL")
    assert ana.get("/telas").status_code == 403

    vencido = codigo_do_qr(logado, "telas")
    with app.app_context():
        conexao = db.obter()
        with conexao:
            conexao.execute("UPDATE autorizacoes SET criado_em = '2020-01-01 00:00:00' WHERE codigo = ?", (vencido,))
    assert "venceu" in bia.get(f"/autorizacao/{vencido}", follow_redirects=True).get_data(as_text=True)
    digitado = codigo_do_qr(logado, "telas")
    resposta = post(bia, "/autorizacao/codigo", {"codigo": digitado.lower()}, follow_redirects=True)
    assert "Autorizado por admin" in resposta.get_data(as_text=True)


def test_codigo_de_outra_loja_nao_vale(logado, app):
    criar_editor(app)
    permitir(logado, **{"telas.editor": permissoes.AUTORIZACAO})
    postar(logado, "/plataforma/empresas/nova", {"nome": "Outra", "usuario": "outro", "senha": "senha-do-editor"},
           pagina="/plataforma/")
    outro = pessoa(app, "outro")
    codigo = codigo_do_qr(outro, "telas")
    ana = pessoa(app, "ana")
    assert "não vale" in ana.get(f"/autorizacao/{codigo}", follow_redirects=True).get_data(as_text=True)


def test_uma_vez_e_sem_prazo(logado, app):
    criar_editor(app)
    permitir(logado, **{"telas.editor": permissoes.AUTORIZACAO})
    ana = pessoa(app, "ana")
    assert "Sem prazo" in logado.get("/autorizar?funcao=telas").get_data(as_text=True)

    ana.get(f"/autorizacao/{codigo_do_qr(logado, 'telas', 'uma')}")
    post(ana, "/telas/nova", {"nome": "Primeira"})
    assert post(ana, "/telas/nova", {"nome": "Segunda"}).status_code == 403
    assert [t["nome"] for t in consultar(app, "SELECT nome FROM telas")] == ["Primeira"]

    ana.get(f"/autorizacao/{codigo_do_qr(logado, 'telas', 'sempre')}")
    ana = pessoa(app, "ana")  # saiu e entrou de novo: continua valendo
    post(ana, "/telas/nova", {"nome": "Segunda"})
    post(ana, "/telas/nova", {"nome": "Terceira"})
    assert len(consultar(app, "SELECT * FROM telas")) == 3
    liberacao = consultar(app, "SELECT id FROM autorizacoes WHERE modo = 'sempre'")[0][0]
    assert "sem prazo" in logado.get("/autorizar").get_data(as_text=True)
    post(logado, f"/autorizar/{liberacao}/encerrar")
    assert ana.get("/telas").status_code == 403
