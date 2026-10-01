"""Cadastro das propagandas (área restrita)."""

import logging
import os
import uuid
from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from . import db
from .auth import login_obrigatorio
from .midia import EXTENSOES, detectar_tipo, extensao_de

bp = Blueprint("painel", __name__)
log = logging.getLogger("propagandas.painel")

DURACAO_PADRAO = 10


def esta_no_ar(item, hoje=None):
    """Diz se a propaganda deve aparecer hoje (ativa e dentro do período)."""
    hoje = (hoje or date.today()).isoformat()
    if not item["ativo"]:
        return False
    if item["inicio"] and hoje < item["inicio"]:
        return False
    if item["fim"] and hoje > item["fim"]:
        return False
    return True


def ler_duracao(valor):
    try:
        return max(1, min(3600, int(valor)))
    except (TypeError, ValueError):
        return DURACAO_PADRAO


def ler_data(valor):
    """Aceita só datas AAAA-MM-DD válidas; qualquer outra coisa vira vazio."""
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return date.fromisoformat(valor).isoformat()
    except ValueError:
        return None


def buscar(conexao, propaganda_id):
    item = conexao.execute("SELECT * FROM propagandas WHERE id = ?", (propaganda_id,)).fetchone()
    if item is None:
        abort(404)
    return item


@bp.route("/")
@login_obrigatorio()
def lista():
    conexao = db.obter()
    itens = conexao.execute("SELECT * FROM propagandas ORDER BY posicao, id").fetchall()
    no_ar = {item["id"]: esta_no_ar(item) for item in itens}
    return render_template(
        "propagandas.html",
        itens=itens,
        no_ar=no_ar,
        letreiro=db.ler_config("letreiro"),
        extensoes=", ".join(sorted(e.upper() for e in EXTENSOES)),
    )


@bp.route("/enviar", methods=["POST"])
@login_obrigatorio()
def enviar():
    conexao = db.obter()
    duracao = ler_duracao(request.form.get("duracao"))
    pasta = current_app.config["PASTA_MIDIA"]
    enviados = 0

    for arquivo in request.files.getlist("arquivos"):
        if not arquivo or not arquivo.filename:
            continue
        nome_original = os.path.basename(arquivo.filename)[:200]
        extensao = extensao_de(nome_original)
        cabecalho = arquivo.stream.read(32)
        arquivo.stream.seek(0)
        tipo = detectar_tipo(cabecalho)
        if extensao not in EXTENSOES or tipo != EXTENSOES[extensao]:
            flash(f"“{nome_original}” foi ignorado: o formato não é suportado ou o arquivo está corrompido.", "erro")
            log.warning("Envio recusado: “%s” por “%s”", nome_original, g.usuario["usuario"])
            continue

        # O nome no disco é aleatório: nunca usamos o nome enviado como caminho.
        nome_disco = f"{uuid.uuid4().hex}.{extensao}"
        caminho = os.path.join(pasta, nome_disco)
        arquivo.save(caminho)
        try:
            with conexao:
                conexao.execute(
                    "INSERT INTO propagandas (nome, arquivo, tipo, duracao, posicao) "
                    "VALUES (?, ?, ?, ?, (SELECT COALESCE(MAX(posicao), 0) + 1 FROM propagandas))",
                    (nome_original, nome_disco, tipo, duracao),
                )
        except Exception:
            os.remove(caminho)
            raise
        enviados += 1
        log.info("“%s” enviou “%s” (%s)", g.usuario["usuario"], nome_original, nome_disco)

    if enviados:
        flash(f"{enviados} propaganda(s) adicionada(s).", "ok")
    return redirect(url_for("painel.lista"))


@bp.route("/propaganda/<int:propaganda_id>/atualizar", methods=["POST"])
@login_obrigatorio()
def atualizar(propaganda_id):
    conexao = db.obter()
    item = buscar(conexao, propaganda_id)
    nome = request.form.get("nome", "").strip()[:200] or item["nome"]
    inicio = ler_data(request.form.get("inicio"))
    fim = ler_data(request.form.get("fim"))
    if inicio and fim and fim < inicio:
        flash("A data de término não pode ser antes da data de início.", "erro")
        return redirect(url_for("painel.lista"))
    with conexao:
        conexao.execute(
            "UPDATE propagandas SET nome = ?, duracao = ?, ativo = ?, inicio = ?, fim = ? WHERE id = ?",
            (
                nome,
                ler_duracao(request.form.get("duracao")),
                1 if request.form.get("ativo") == "on" else 0,
                inicio,
                fim,
                propaganda_id,
            ),
        )
    log.info("“%s” alterou a propaganda “%s”", g.usuario["usuario"], nome)
    flash("Alterações salvas.", "ok")
    return redirect(url_for("painel.lista"))


@bp.route("/propaganda/<int:propaganda_id>/mover/<direcao>", methods=["POST"])
@login_obrigatorio()
def mover(propaganda_id, direcao):
    if direcao not in ("cima", "baixo"):
        abort(404)
    conexao = db.obter()
    itens = conexao.execute("SELECT id FROM propagandas ORDER BY posicao, id").fetchall()
    ids = [linha["id"] for linha in itens]
    if propaganda_id not in ids:
        abort(404)
    posicao = ids.index(propaganda_id)
    destino = posicao - 1 if direcao == "cima" else posicao + 1
    if 0 <= destino < len(ids):
        ids[posicao], ids[destino] = ids[destino], ids[posicao]
        with conexao:
            conexao.executemany(
                "UPDATE propagandas SET posicao = ? WHERE id = ?",
                [(numero, item_id) for numero, item_id in enumerate(ids, start=1)],
            )
    return redirect(url_for("painel.lista"))


@bp.route("/propaganda/<int:propaganda_id>/excluir", methods=["POST"])
@login_obrigatorio()
def excluir(propaganda_id):
    conexao = db.obter()
    item = buscar(conexao, propaganda_id)
    with conexao:
        conexao.execute("DELETE FROM propagandas WHERE id = ?", (propaganda_id,))
    caminho = os.path.join(current_app.config["PASTA_MIDIA"], item["arquivo"])
    if os.path.exists(caminho):
        os.remove(caminho)
    log.info("“%s” excluiu a propaganda “%s”", g.usuario["usuario"], item["nome"])
    flash("Propaganda excluída.", "ok")
    return redirect(url_for("painel.lista"))


@bp.route("/letreiro", methods=["POST"])
@login_obrigatorio()
def letreiro():
    texto = request.form.get("letreiro", "").strip()[:500]
    db.gravar_config("letreiro", texto)
    log.info("“%s” alterou o letreiro", g.usuario["usuario"])
    flash("Letreiro salvo.", "ok")
    return redirect(url_for("painel.lista"))
