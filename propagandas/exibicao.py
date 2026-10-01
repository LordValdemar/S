"""Tela de exibição (TV) e API pública da playlist."""

from flask import Blueprint, current_app, jsonify, render_template, send_from_directory, url_for

from . import db
from .painel import esta_no_ar

bp = Blueprint("exibicao", __name__)

UM_ANO = 365 * 24 * 3600


@bp.route("/player")
def player():
    return render_template("player.html")


@bp.route("/api/playlist")
def playlist():
    conexao = db.obter()
    itens = conexao.execute("SELECT * FROM propagandas ORDER BY posicao, id").fetchall()
    resposta = jsonify({
        "itens": [
            {
                "id": item["id"],
                "tipo": item["tipo"],
                "url": url_for("exibicao.midia", arquivo=item["arquivo"]),
                "duracao": item["duracao"],
            }
            for item in itens
            if esta_no_ar(item)
        ],
        "letreiro": db.ler_config("letreiro"),
    })
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


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
