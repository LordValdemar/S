"""Administração da plataforma: empresas clientes, planos e suspensão (só para o dono do sistema).

As regras vêm do núcleo (src/domain/empresas/plataforma.py); aqui ficam a lista e as rotas.
"""

import logging
import os

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from src.domain.empresas import CadastroInvalido, DadosDaEmpresa, Limites, ServicoDaPlataforma
from src.domain.erros import NaoEncontrado
from src.infrastructure.sqlite import RepositorioDaPlataformaSQLite

from . import agenda, alertas, asaas, cobranca, db
from .auth import EMPRESA_PRINCIPAL, ErroUsuario, criar_usuario, plataforma_obrigatoria
from .planos import MB

bp = Blueprint("plataforma", __name__, url_prefix="/plataforma")
log = logging.getLogger("propagandas.plataforma")


def _ler_limite(nome):
    """Campo vazio = sem limite."""
    valor = request.form.get(nome, "").strip()
    return int(valor) if valor.isdigit() else None


def _dados_do_formulario():
    return DadosDaEmpresa(nome=request.form.get("nome", ""),
                          limites=Limites(_ler_limite("limite_telas"), _ler_limite("limite_mb")), modulos_liberados="")


def servico(conexao=None):
    return ServicoDaPlataforma(RepositorioDaPlataformaSQLite(conexao or db.obter()), EMPRESA_PRINCIPAL,
                               codigo_livre=lambda _nome: "")


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
    telas = conexao.execute("SELECT empresa_id, ultimo_contato, fechada_em FROM telas").fetchall()
    resumo_telas = {}
    for tela in telas:
        contagem = resumo_telas.setdefault(tela["empresa_id"], {"total": 0, "online": 0})
        contagem["total"] += 1
        contagem["online"] += alertas.esta_online(tela)
    faturas = {}
    for fatura in conexao.execute(
        "SELECT * FROM faturas WHERE status != 'DELETED' ORDER BY vencimento DESC"
    ).fetchall():
        lista_empresa = faturas.setdefault(fatura["empresa_id"], [])
        if len(lista_empresa) < 6:
            lista_empresa.append(fatura)
    return render_template(
        "plataforma.html",
        empresas=empresas,
        telas=resumo_telas,
        MB=MB,
        principal=EMPRESA_PRINCIPAL,
        planos=conexao.execute("SELECT * FROM planos ORDER BY preco_centavos").fetchall(),
        faturas=faturas,
        STATUS=cobranca.STATUS,
        asaas_configurado=asaas.configurado(),
        ambiente=current_app.config["ASAAS_AMBIENTE"],
        hoje=agenda.agora_local().date(),
        receita=conexao.execute(
            "SELECT COALESCE(SUM(p.preco_centavos), 0) FROM empresas e JOIN planos p ON p.id = e.plano_id "
            "WHERE e.asaas_assinatura_id IS NOT NULL AND e.ativa = 1"
        ).fetchone()[0],
    )


@bp.route("/empresas/nova", methods=["POST"])
@plataforma_obrigatoria
def nova():
    conexao = db.obter()
    try:
        empresa_id, _ = servico(conexao).criar(
            _dados_do_formulario(),
            lambda empresa_id: criar_usuario(conexao, empresa_id, request.form.get("usuario", ""),
                                             request.form.get("senha", ""), "admin"))
    except CadastroInvalido as erro:
        flash(str(erro), "erro")
    except ErroUsuario as erro:
        flash(f"Empresa não criada: {erro}", "erro")
    else:
        nome = request.form.get("nome", "").strip()[:100]
        log.info("“%s” criou a empresa “%s” (id %s)", g.usuario["usuario"], nome, empresa_id)
        flash(f"Empresa “{nome}” criada. Envie o usuário e a senha para o cliente acessar.", "ok")
    return redirect(url_for("plataforma.lista"))


@bp.route("/empresas/<int:empresa_id>/atualizar", methods=["POST"])
@plataforma_obrigatoria
def atualizar(empresa_id):
    try:
        empresa, mudou = servico().atualizar(empresa_id, _dados_do_formulario(), ativa=request.form.get("ativa") == "on")
    except NaoEncontrado:
        abort(404)
    if mudou:
        log.warning("“%s” %s a empresa “%s”", g.usuario["usuario"], "SUSPENDEU" if empresa.ativa else "reativou", empresa.nome)
    flash("Empresa atualizada.", "ok")
    return redirect(url_for("plataforma.lista"))


def _cancelar_assinatura(empresa_id):
    """Sem isso o Asaas continuaria cobrando um cliente que não existe mais."""
    empresa = db.obter().execute("SELECT asaas_assinatura_id FROM empresas WHERE id = ?", (empresa_id,)).fetchone()
    asaas.cancelar_assinatura(empresa["asaas_assinatura_id"])


def _apagar_midia(arquivo):
    caminho = os.path.join(current_app.config["PASTA_MIDIA"], arquivo)
    if os.path.exists(caminho):
        os.remove(caminho)


@bp.route("/empresas/<int:empresa_id>/excluir", methods=["POST"])
@plataforma_obrigatoria
def excluir(empresa_id):
    try:
        empresa = servico().excluir(empresa_id, request.form.get("confirmacao", ""), _cancelar_assinatura, _apagar_midia)
    except NaoEncontrado:
        abort(404)
    except asaas.ErroAsaas as erro:
        flash(f"Não foi possível cancelar a assinatura no Asaas ({erro}). A empresa não foi excluída.", "erro")
    except CadastroInvalido as erro:
        flash(str(erro), "erro")
    else:
        log.warning("“%s” EXCLUIU a empresa “%s” (id %s) e todos os seus dados", g.usuario["usuario"], empresa.nome,
                    empresa_id)
        flash(f"Empresa “{empresa.nome}” e todos os seus dados foram excluídos.", "ok")
    return redirect(url_for("plataforma.lista"))
