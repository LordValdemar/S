"""Varredura de isolamento: percorre TODAS as rotas do sistema tentando alcançar dados alheios.

Duas lojas clientes. O administrador da loja invasora usa os números (ids) dos registros da
loja vítima em cada rota, com todas as ações conhecidas; e um editor da própria vítima tenta
as rotas que são só do administrador. Nada da vítima pode mudar, e nenhuma
página pode mostrar os dados dela. Rotas novas entram na varredura sozinhas.
"""

import re

import pytest

from conftest import PNG, conectar_tv, enviar, postar
from propagandas import auth, db

SEGREDO = "SEGREDO-DA-VITIMA"
ACOES = ["", "excluir", "ativar", "desativar", "tempo", "telas", "letreiro", "pausar", "subir", "descer"]

# Rotas sem id de registro (ou com segredo próprio na URL) que têm testes específicos em outros arquivos.
FORA_DA_VARREDURA = {"static", "exibicao.midia", "auth.entrar_na_loja", "exibicao.conectar", "exibicao.conectar_nova", "auth.sair",
                     "cobranca.webhook_asaas"}

# O que um editor não pode fazer (é do administrador da loja ou da plataforma).
SO_ADMINISTRACAO = re.compile(
    r"^(empresa|plataforma)\.|^cobranca\.(salvar|ativar|cancelar|sincronizar|atualizar|novo)|"
    r"^telas\.(lista|nova|atualizar|trocar_codigo|desconectar_aparelho|excluir|novo_grupo|excluir_grupo|testar_alerta)$|"
    r"^auth\.(usuarios|novo_usuario|editar_usuario|excluir_usuario|desativar_2fa_usuario)$|^conta\.(assinar|cancelar)$"
)


def consultar(app, sql, *parametros):
    with app.app_context():
        return db.obter().execute(sql, parametros).fetchall()


def token(cliente):
    with cliente.session_transaction() as sessao:
        sessao.setdefault("csrf", "token-de-teste")
        return sessao["csrf"]


def entrar(app, usuario, senha="senha-da-loja-123"):
    cliente = app.test_client()
    cliente.post("/login", data={"usuario": usuario, "senha": senha, "csrf_token": token(cliente)})
    assert cliente.get("/conta").status_code == 200, usuario
    return cliente


def criar_loja(plataforma, nome, usuario):
    postar(plataforma, "/plataforma/empresas/nova",
           {"nome": nome, "usuario": usuario, "senha": "senha-da-loja-123"}, pagina="/plataforma/")
    return consultar(plataforma.application, "SELECT id FROM empresas WHERE nome = ?", nome)[0]["id"]


def foto(app, empresa_id):
    """Tudo o que pertence à empresa (e o que é de todas), para comparar antes e depois."""
    with app.app_context():
        conexao = db.obter()
        tabelas = [t for (t,) in conexao.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        retrato = {}
        for tabela in tabelas:
            colunas = [c[1] for c in conexao.execute(f"PRAGMA table_info({tabela})")]
            if "empresa_id" in colunas:
                linhas = conexao.execute(f"SELECT * FROM {tabela} WHERE empresa_id = ?", (empresa_id,))
            elif tabela == "empresas":
                linhas = conexao.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
            elif tabela in ("propaganda_destinos", "planos"):
                linhas = conexao.execute(f"SELECT * FROM {tabela}")
            else:
                continue
            retrato[tabela] = sorted(tuple(linha) for linha in linhas)
        return retrato


@pytest.fixture
def lojas(logado):
    app = logado.application
    vitima_id = criar_loja(logado, "Loja Vítima", "vitima")
    criar_loja(logado, "Loja Invasora", "invasor")
    vitima = entrar(app, "vitima")
    with app.app_context():
        auth.criar_usuario(db.obter(), vitima_id, "editor-vitima", "senha-da-loja-123", "editor")

    # Dados da vítima em todos os módulos.
    enviar(vitima, f"{SEGREDO}.png", PNG)
    postar(vitima, "/telas/nova", {"nome": f"TV {SEGREDO}"}, pagina="/telas")
    postar(vitima, "/grupos/novo", {"nome": f"Grupo {SEGREDO}"}, pagina="/telas")
    tela = consultar(app, "SELECT * FROM telas WHERE empresa_id = ?", vitima_id)[0]
    conectar_tv(vitima, tela["id"])

    ids = {
        "propaganda_id": consultar(app, "SELECT id FROM propagandas WHERE empresa_id = ?", vitima_id)[0]["id"],
        "tela_id": tela["id"],
        "grupo_id": consultar(app, "SELECT id FROM grupos WHERE empresa_id = ?", vitima_id)[0]["id"],
        "usuario_id": consultar(app, "SELECT id FROM usuarios WHERE usuario = 'vitima'")[0]["id"],
        "empresa_id": vitima_id, "plano_id": 1,
        "direcao": "cima", "codigo": tela["codigo"],
    }
    formulario = {
        "nome": "invadido", "duracao": "5",
        "ativo": "on", "dias": list("0123456"), "destino": "todas", "tela_id": str(tela["id"]),
        "codigo": "invadido", "usuario": "intruso", "senha": "senha-do-intruso-1", "papel": "admin",
        "ids": [str(ids["propaganda_id"])], "modo": "trocar", "letreiro": "invadido",
    }
    return app, vitima_id, ids, formulario


def rotas(app):
    for regra in app.url_map.iter_rules():
        if regra.endpoint in FORA_DA_VARREDURA:
            continue
        yield regra


def atacar(cliente, regra, ids, formulario):
    """Chama a rota com os ids da vítima, em todas as ações. Devolve as respostas."""
    url = regra.build({nome: ids[nome] for nome in regra.arguments}, append_unknown=False)[1] \
        if regra.arguments else regra.rule
    respostas = []
    if "GET" in regra.methods:
        respostas.append(("GET", url, cliente.get(url)))
    if "POST" in regra.methods:
        for acao in ACOES:
            dados = {**formulario, "acao": acao, "csrf_token": token(cliente)}
            respostas.append((f"POST {acao}", url, cliente.post(url, data=dados)))
    return respostas


def test_outra_loja_nao_alcanca_nada_em_nenhuma_rota(lojas):
    app, vitima_id, ids, formulario = lojas
    invasor = entrar(app, "invasor")
    antes = foto(app, vitima_id)  # depois de entrar: abrir /conta prepara o segredo da 2FA de quem entra
    for regra in rotas(app):
        if regra.endpoint == "auth.login_codigo" or regra.endpoint == "auth.configurar":
            continue
        for metodo, url, resposta in atacar(invasor, regra, ids, formulario):
            pagina = resposta.get_data()  # bytes: a exportação é um .zip (coberta em test_empresas)
            assert SEGREDO.encode() not in pagina, (metodo, url)
            assert ids["codigo"].encode() not in pagina, (metodo, url)
        assert foto(app, vitima_id) == antes, regra.rule
        # A invasora continua logada (nenhuma rota a derruba sem querer, o que esconderia falhas).
        if invasor.get("/conta").status_code != 200:
            invasor = entrar(app, "invasor")


def test_editor_nao_usa_rotas_da_administracao(lojas):
    app, vitima_id, ids, formulario = lojas
    editor = entrar(app, "editor-vitima")
    antes = foto(app, vitima_id)  # depois de entrar: abrir /conta prepara o segredo da 2FA de quem entra
    for regra in rotas(app):
        if not SO_ADMINISTRACAO.match(regra.endpoint):
            continue
        for metodo, url, resposta in atacar(editor, regra, ids, formulario):
            if metodo == "GET":
                assert resposta.status_code in (302, 403, 404), (metodo, url, resposta.status_code)
        assert foto(app, vitima_id) == antes, regra.rule


def test_tv_de_outra_loja_nao_pareia_nem_le_a_tela_da_vitima(lojas):
    app, vitima_id, ids, _ = lojas
    invasor = entrar(app, "invasor")
    tela = consultar(app, "SELECT * FROM telas WHERE id = ?", ids["tela_id"])[0]

    # Um aparelho qualquer abre /tela; o invasor tenta ligá-lo à tela da vítima.
    aparelho = app.test_client()
    codigo = re.search(r'<p class="relogio">([A-Z0-9]{6})</p>', aparelho.get("/tela").get_data(as_text=True)).group(1)
    invasor.post(f"/tela/parear/{codigo}", data={"tela_id": str(ids["tela_id"]), "csrf_token": token(invasor)})
    invasor.post("/telas/conectar", data={"codigo": codigo, "tela_id": str(ids["tela_id"]),
                                          "csrf_token": token(invasor)})
    assert not aparelho.get("/api/tela/conexao").get_json().get("pronto")
    assert consultar(app, "SELECT aparelho_hash FROM telas WHERE id = ?", ids["tela_id"])[0][0] == tela["aparelho_hash"]

    # Sem o crachá do aparelho, o endereço da tela não mostra nada, nem a lista de propagandas.
    for cliente in (invasor, app.test_client()):
        assert SEGREDO not in cliente.get(f"/tela/{tela['codigo']}").get_data(as_text=True)
        assert cliente.get(f"/api/tela/{tela['codigo']}/playlist").status_code == 403
        assert cliente.post(f"/api/tela/{tela['codigo']}/pulso", json={}).status_code == 403
