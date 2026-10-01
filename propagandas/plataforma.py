"""Administração da plataforma: empresas clientes, planos e suspensão (só para o dono do sistema)."""

import logging
import os

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from . import alertas, db
from .auth import EMPRESA_PRINCIPAL, ErroUsuario, criar_usuario, plataforma_obrigatoria
from .planos import MB

bp = Blueprint("plataforma", __name__, url_prefix="/plataforma")
log = logging.getLogger("propagandas.plataforma")


def _ler_limite(nome):
    """Campo vazio = sem limite."""
    valor = request.form.get(nome, "").strip()
    return int(valor) if valor.isdigit() else None


def _buscar(conexao, empresa_id):
    empresa = conexao.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,)).fetchone()
    if empresa is None:
        abort(404)
    return empresa


@bp.route("/")
@plataforma_obrigatoria
def lista():
    conexao = db.obter()
    empresas = conexao.execute(
        """
        SELECT e.*,
               (SELECT COUNT(*) FROM usuarios u WHERE u.empresa_id = e.id) AS usuarios,
               (SELECT COUNT(*) FROM propagandas p WHERE p.empresa_id = e.id) AS propagandas,
               (SELECT COALESCE(SUM(tamanho), 0) FROM propagandas p WHERE p.empresa_id = e.id) AS bytes
        FROM empresas e ORDER BY e.id
        """
    ).fetchall()
    telas = conexao.execute("SELECT empresa_id, ultimo_contato FROM telas").fetchall()
    resumo_telas = {}
    for tela in telas:
        contagem = resumo_telas.setdefault(tela["empresa_id"], {"total": 0, "online": 0})
        contagem["total"] += 1
        contagem["online"] += alertas.esta_online(tela)
    return render_template(
        "plataforma.html", empresas=empresas, telas=resumo_telas, MB=MB, principal=EMPRESA_PRINCIPAL
    )


@bp.route("/empresas/nova", methods=["POST"])
@plataforma_obrigatoria
def nova():
    conexao = db.obter()
    nome = request.form.get("nome", "").strip()[:100]
    if not nome:
        flash("Informe o nome da empresa.", "erro")
        return redirect(url_for("plataforma.lista"))
    with conexao:
        empresa_id = conexao.execute(
            "INSERT INTO empresas (nome, limite_telas, limite_mb) VALUES (?, ?, ?)",
            (nome, _ler_limite("limite_telas"), _ler_limite("limite_mb")),
        ).lastrowid
    try:
        criar_usuario(conexao, empresa_id, request.form.get("usuario", ""), request.form.get("senha", ""), "admin")
    except ErroUsuario as erro:
        with conexao:
            conexao.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
        flash(f"Empresa não criada: {erro}", "erro")
        return redirect(url_for("plataforma.lista"))
    log.info("“%s” criou a empresa “%s” (id %s)", g.usuario["usuario"], nome, empresa_id)
    flash(f"Empresa “{nome}” criada. Envie o usuário e a senha para o cliente acessar.", "ok")
    return redirect(url_for("plataforma.lista"))


@bp.route("/empresas/<int:empresa_id>/atualizar", methods=["POST"])
@plataforma_obrigatoria
def atualizar(empresa_id):
    conexao = db.obter()
    empresa = _buscar(conexao, empresa_id)
    ativa = request.form.get("ativa") == "on"
    if empresa_id == EMPRESA_PRINCIPAL:
        ativa = True  # a empresa principal (a sua) nunca é suspensa
    with conexao:
        conexao.execute(
            "UPDATE empresas SET nome = ?, limite_telas = ?, limite_mb = ?, ativa = ? WHERE id = ?",
            (
                request.form.get("nome", "").strip()[:100] or empresa["nome"],
                _ler_limite("limite_telas"),
                _ler_limite("limite_mb"),
                1 if ativa else 0,
                empresa_id,
            ),
        )
    if bool(empresa["ativa"]) != ativa:
        log.warning("“%s” %s a empresa “%s”", g.usuario["usuario"], "reativou" if ativa else "SUSPENDEU", empresa["nome"])
    flash("Empresa atualizada.", "ok")
    return redirect(url_for("plataforma.lista"))


@bp.route("/empresas/<int:empresa_id>/excluir", methods=["POST"])
@plataforma_obrigatoria
def excluir(empresa_id):
    conexao = db.obter()
    empresa = _buscar(conexao, empresa_id)
    if empresa_id == EMPRESA_PRINCIPAL:
        flash("A empresa principal não pode ser excluída.", "erro")
        return redirect(url_for("plataforma.lista"))
    if request.form.get("confirmacao", "").strip() != empresa["nome"]:
        flash("Para excluir, digite o nome exato da empresa.", "erro")
        return redirect(url_for("plataforma.lista"))

    arquivos = [linha["arquivo"] for linha in conexao.execute(
        "SELECT arquivo FROM propagandas WHERE empresa_id = ?", (empresa_id,)
    )]
    with conexao:
        # ON DELETE CASCADE apaga usuários, telas, grupos, propagandas, configurações e exibições.
        conexao.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
    for arquivo in arquivos:
        caminho = os.path.join(current_app.config["PASTA_MIDIA"], arquivo)
        if os.path.exists(caminho):
            os.remove(caminho)
    log.warning("“%s” EXCLUIU a empresa “%s” (id %s) e todos os seus dados", g.usuario["usuario"], empresa["nome"], empresa_id)
    flash(f"Empresa “{empresa['nome']}” e todos os seus dados foram excluídos.", "ok")
    return redirect(url_for("plataforma.lista"))
