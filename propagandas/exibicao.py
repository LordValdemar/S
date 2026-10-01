"""Tela de exibição (TV), API das telas e registro das exibições."""

from datetime import datetime, timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from . import agenda, db
from .auth import csrf_isento

bp = Blueprint("exibicao", __name__)

UM_ANO = 365 * 24 * 3600
MAX_REGISTROS_POR_ENVIO = 1000


def propagandas_no_ar(tela=None):
    """Propagandas que devem aparecer agora na tela (ou no player geral, se tela=None)."""
    conexao = db.obter()
    agora = agenda.agora_local()
    itens = conexao.execute("SELECT * FROM propagandas ORDER BY posicao, id").fetchall()
    permitidas = set()
    if tela is not None:
        permitidas = {
            linha["propaganda_id"]
            for linha in conexao.execute(
                "SELECT propaganda_id FROM propaganda_destinos WHERE tela_id = ? OR grupo_id = ?",
                (tela["id"], tela["grupo_id"]),
            )
        }
    return [
        item for item in itens
        if agenda.esta_no_ar(item, agora) and (item["para_todas"] or item["id"] in permitidas)
    ]


def _resposta_playlist(itens, letreiro):
    resposta = jsonify({
        "itens": [
            {
                "id": item["id"],
                "tipo": item["tipo"],
                "url": url_for("exibicao.midia", arquivo=item["arquivo"]),
                "duracao": item["duracao"],
            }
            for item in itens
        ],
        "letreiro": letreiro,
    })
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def _buscar_tela(codigo):
    tela = db.obter().execute("SELECT * FROM telas WHERE codigo = ?", (codigo,)).fetchone()
    if tela is None:
        abort(404)
    return tela


def _registrar_contato(tela, **extras):
    campos = {
        "ultimo_contato": agenda.para_texto_utc(agenda.agora_utc()),
        "ultimo_ip": (request.remote_addr or "")[:45],
        "navegador": request.headers.get("User-Agent", "")[:200],
        **extras,
    }
    conexao = db.obter()
    with conexao:
        conexao.execute(
            f"UPDATE telas SET {', '.join(f'{c} = ?' for c in campos)} WHERE id = ?",
            (*campos.values(), tela["id"]),
        )


# ---------------------------------------------------------------------------
# Player geral (sem cadastro de tela): mostra só o que é "para todas as telas"
# ---------------------------------------------------------------------------

@bp.route("/player")
def player():
    return render_template("player.html", api=url_for("exibicao.playlist"), pulso="")


@bp.route("/api/playlist")
def playlist():
    return _resposta_playlist(propagandas_no_ar(), db.ler_config("letreiro"))


# ---------------------------------------------------------------------------
# Telas cadastradas: cada TV usa o próprio endereço /tela/<código>
# ---------------------------------------------------------------------------

@bp.route("/tela/<codigo>")
def tela(codigo):
    tela = db.obter().execute("SELECT id FROM telas WHERE codigo = ?", (codigo,)).fetchone()
    if tela is None:
        return render_template("tela_desconhecida.html"), 404
    return render_template(
        "player.html",
        api=url_for("exibicao.playlist_tela", codigo=codigo),
        pulso=url_for("exibicao.pulso", codigo=codigo),
    )


@bp.route("/api/tela/<codigo>/playlist")
def playlist_tela(codigo):
    tela = _buscar_tela(codigo)
    _registrar_contato(tela)
    letreiro = tela["letreiro"] if tela["letreiro"] else db.ler_config("letreiro")
    return _resposta_playlist(propagandas_no_ar(tela), letreiro)


def _ler_registro(registro, agora, mais_antigo):
    """Valida um registro de exibição enviado pela TV. Retorna (id, inicio_utc, duracao) ou None."""
    if not isinstance(registro, dict):
        return None
    try:
        propaganda_id = int(registro["propaganda_id"])
        duracao = float(registro["duracao"])
        inicio = datetime.fromisoformat(str(registro["inicio"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None
    if inicio.tzinfo is None or not 0 < duracao <= 86400:
        return None
    if not mais_antigo <= inicio <= agora + timedelta(hours=1):  # relógio da TV muito errado
        return None
    return propaganda_id, agenda.para_texto_utc(inicio), round(duracao, 1)


@bp.route("/api/tela/<codigo>/pulso", methods=["POST"])
@csrf_isento
def pulso(codigo):
    """A TV avisa que está viva, o que está exibindo e o que já exibiu."""
    tela = _buscar_tela(codigo)
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        abort(400)
    registros = dados.get("exibicoes") or []
    if not isinstance(registros, list):
        abort(400)
    registros = registros[:MAX_REGISTROS_POR_ENVIO]

    conexao = db.obter()
    nomes = {linha["id"]: linha["nome"] for linha in conexao.execute("SELECT id, nome FROM propagandas")}
    agora = agenda.agora_utc()
    mais_antigo = agora - timedelta(days=current_app.config["RETER_EXIBICOES_DIAS"])

    linhas = []
    for registro in registros:
        lido = _ler_registro(registro, agora, mais_antigo)
        if lido:
            propaganda_id, inicio, duracao = lido
            nome = nomes.get(propaganda_id, "(propaganda excluída)")
            linhas.append((tela["id"], propaganda_id, nome, inicio, duracao))
    with conexao:
        # OR IGNORE: se a TV reenviar o mesmo registro (queda de rede), não duplica.
        conexao.executemany(
            "INSERT OR IGNORE INTO exibicoes (tela_id, propaganda_id, propaganda_nome, exibido_em, duracao) "
            "VALUES (?, ?, ?, ?, ?)",
            linhas,
        )

    exibindo = dados.get("exibindo")
    nome_exibindo = nomes.get(exibindo) if isinstance(exibindo, int) else None
    _registrar_contato(tela, exibindo=nome_exibindo)
    return {"recebidos": len(registros), "gravados": len(linhas)}


# ---------------------------------------------------------------------------
# Arquivos e monitoramento
# ---------------------------------------------------------------------------

@bp.route("/midia/<arquivo>")
def midia(arquivo):
    # Os nomes no disco são únicos e nunca mudam, então a TV pode guardar
    # o arquivo em cache por muito tempo (economiza rede e aguenta quedas).
    resposta = send_from_directory(current_app.config["PASTA_MIDIA"], arquivo, max_age=UM_ANO)
    resposta.headers["Cache-Control"] = f"public, max-age={UM_ANO}, immutable"
    return resposta


@bp.route("/saude")
def saude():
    """Para monitoramento: responde 200 se o servidor e o banco estão ok."""
    db.obter().execute("SELECT 1").fetchone()
    return {"status": "ok"}
