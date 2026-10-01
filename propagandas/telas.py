"""Cadastro das telas (TVs), grupos e monitoramento (somente administradores)."""

import logging
import secrets

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from . import alertas, db
from .auth import login_obrigatorio

bp = Blueprint("telas", __name__)
log = logging.getLogger("propagandas.telas")


def novo_codigo():
    # Difícil de adivinhar: quem não tem o código não vê nem registra nada da tela.
    return secrets.token_urlsafe(9)


def _ler_grupo(conexao):
    valor = request.form.get("grupo_id", "")
    if not valor.isdigit():
        return None
    linha = conexao.execute("SELECT id FROM grupos WHERE id = ?", (int(valor),)).fetchone()
    return linha["id"] if linha else None


def _buscar(conexao, tela_id):
    tela = conexao.execute("SELECT * FROM telas WHERE id = ?", (tela_id,)).fetchone()
    if tela is None:
        abort(404)
    return tela


@bp.route("/telas")
@login_obrigatorio("admin")
def lista():
    conexao = db.obter()
    telas = conexao.execute(
        "SELECT t.*, gr.nome AS grupo_nome FROM telas t LEFT JOIN grupos gr ON gr.id = t.grupo_id ORDER BY t.nome"
    ).fetchall()
    online = {t["id"]: alertas.esta_online(t) for t in telas}
    return render_template(
        "telas.html",
        telas=telas,
        online=online,
        offline=sum(1 for t in telas if t["ultimo_contato"] and not online[t["id"]]),
        grupos=conexao.execute(
            "SELECT gr.*, COUNT(t.id) AS total FROM grupos gr LEFT JOIN telas t ON t.grupo_id = gr.id "
            "GROUP BY gr.id ORDER BY gr.nome"
        ).fetchall(),
        canais=alertas.canais_configurados(current_app.config),
        letreiro_geral=db.ler_config("letreiro"),
    )


@bp.route("/telas/nova", methods=["POST"])
@login_obrigatorio("admin")
def nova():
    conexao = db.obter()
    nome = request.form.get("nome", "").strip()[:100]
    if not nome:
        flash("Dê um nome para a tela (ex.: “Balcão”, “Vitrine”).", "erro")
        return redirect(url_for("telas.lista"))
    with conexao:
        conexao.execute(
            "INSERT INTO telas (nome, codigo, grupo_id) VALUES (?, ?, ?)",
            (nome, novo_codigo(), _ler_grupo(conexao)),
        )
    log.info("“%s” cadastrou a tela “%s”", g.usuario["usuario"], nome)
    flash(f"Tela “{nome}” cadastrada. Abra o endereço dela na TV.", "ok")
    return redirect(url_for("telas.lista"))


@bp.route("/telas/<int:tela_id>/atualizar", methods=["POST"])
@login_obrigatorio("admin")
def atualizar(tela_id):
    conexao = db.obter()
    tela = _buscar(conexao, tela_id)
    nome = request.form.get("nome", "").strip()[:100] or tela["nome"]
    letreiro = request.form.get("letreiro", "").strip()[:500] or None
    with conexao:
        conexao.execute(
            "UPDATE telas SET nome = ?, grupo_id = ?, letreiro = ? WHERE id = ?",
            (nome, _ler_grupo(conexao), letreiro, tela_id),
        )
    log.info("“%s” alterou a tela “%s”", g.usuario["usuario"], nome)
    flash("Tela atualizada.", "ok")
    return redirect(url_for("telas.lista"))


@bp.route("/telas/<int:tela_id>/novo-codigo", methods=["POST"])
@login_obrigatorio("admin")
def trocar_codigo(tela_id):
    conexao = db.obter()
    tela = _buscar(conexao, tela_id)
    with conexao:
        conexao.execute("UPDATE telas SET codigo = ? WHERE id = ?", (novo_codigo(), tela_id))
    log.info("“%s” gerou novo endereço para a tela “%s”", g.usuario["usuario"], tela["nome"])
    flash(f"Novo endereço gerado para “{tela['nome']}”. O endereço antigo parou de funcionar.", "ok")
    return redirect(url_for("telas.lista"))


@bp.route("/telas/<int:tela_id>/excluir", methods=["POST"])
@login_obrigatorio("admin")
def excluir(tela_id):
    conexao = db.obter()
    tela = _buscar(conexao, tela_id)
    with conexao:
        conexao.execute("DELETE FROM telas WHERE id = ?", (tela_id,))
    log.info("“%s” excluiu a tela “%s”", g.usuario["usuario"], tela["nome"])
    flash("Tela excluída. O histórico de exibições dela foi mantido nos relatórios.", "ok")
    return redirect(url_for("telas.lista"))


@bp.route("/grupos/novo", methods=["POST"])
@login_obrigatorio("admin")
def novo_grupo():
    conexao = db.obter()
    nome = request.form.get("nome", "").strip()[:100]
    if not nome:
        flash("Dê um nome para o grupo (ex.: “Lojas de SP”).", "erro")
    elif conexao.execute("SELECT 1 FROM grupos WHERE nome = ?", (nome,)).fetchone():
        flash(f"O grupo “{nome}” já existe.", "erro")
    else:
        with conexao:
            conexao.execute("INSERT INTO grupos (nome) VALUES (?)", (nome,))
        log.info("“%s” criou o grupo “%s”", g.usuario["usuario"], nome)
        flash("Grupo criado.", "ok")
    return redirect(url_for("telas.lista"))


@bp.route("/grupos/<int:grupo_id>/excluir", methods=["POST"])
@login_obrigatorio("admin")
def excluir_grupo(grupo_id):
    conexao = db.obter()
    grupo = conexao.execute("SELECT * FROM grupos WHERE id = ?", (grupo_id,)).fetchone()
    if grupo is None:
        abort(404)
    with conexao:
        # Propagandas que só iam para este grupo ficam sem destino (não aparecem
        # em lugar nenhum) e o painel avisa. Nunca passam a ir para todas as telas.
        conexao.execute("DELETE FROM grupos WHERE id = ?", (grupo_id,))
    log.info("“%s” excluiu o grupo “%s”", g.usuario["usuario"], grupo["nome"])
    flash("Grupo excluído. As telas dele ficaram sem grupo.", "ok")
    return redirect(url_for("telas.lista"))


@bp.route("/alertas/testar", methods=["POST"])
@login_obrigatorio("admin")
def testar_alerta():
    if not alertas.canais_configurados(current_app.config):
        flash("Nenhum canal de alerta configurado. Veja a seção “Alertas” do README.", "erro")
    else:
        erros = alertas.enviar_alerta(f"🔔 Teste de alerta enviado por {g.usuario['usuario']}.")
        if erros:
            flash("Falha ao enviar: " + "; ".join(erros), "erro")
        else:
            flash("Alerta de teste enviado.", "ok")
    return redirect(url_for("telas.lista"))
