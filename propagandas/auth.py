"""Login, usuários, permissões e proteção CSRF."""

import hmac
import logging
import secrets
import threading
import time
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import db

bp = Blueprint("auth", __name__)
log = logging.getLogger("propagandas.auth")

PAPEIS = {"admin": "Administrador", "editor": "Editor"}
SENHA_MINIMA = 8
MAX_TENTATIVAS = 5
JANELA_BLOQUEIO = 15 * 60  # segundos


class ErroUsuario(ValueError):
    """Dados de usuário inválidos (mensagem pode ser mostrada na tela)."""


# ---------------------------------------------------------------------------
# Regras de usuário (usadas pelo painel e pelo gerenciar.py)
# ---------------------------------------------------------------------------

def validar_senha(senha):
    if len(senha) < SENHA_MINIMA:
        raise ErroUsuario(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")


def criar_usuario(conexao, usuario, senha, papel="editor"):
    usuario = usuario.strip()
    if not usuario or len(usuario) > 50:
        raise ErroUsuario("Informe um nome de usuário (até 50 caracteres).")
    if papel not in PAPEIS:
        raise ErroUsuario("Papel inválido.")
    validar_senha(senha)
    if conexao.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (usuario,)).fetchone():
        raise ErroUsuario(f"O usuário “{usuario}” já existe.")
    with conexao:
        conexao.execute(
            "INSERT INTO usuarios (usuario, senha_hash, papel, token_sessao) VALUES (?, ?, ?, ?)",
            (usuario, generate_password_hash(senha), papel, secrets.token_hex(16)),
        )


def trocar_senha(conexao, usuario_id, senha_nova):
    validar_senha(senha_nova)
    with conexao:
        # Trocar o token derruba as sessões abertas em outros aparelhos.
        conexao.execute(
            "UPDATE usuarios SET senha_hash = ?, token_sessao = ? WHERE id = ?",
            (generate_password_hash(senha_nova), secrets.token_hex(16), usuario_id),
        )


def existe_usuario(conexao):
    return conexao.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone() is not None


# ---------------------------------------------------------------------------
# Limite de tentativas de login (por IP)
# ---------------------------------------------------------------------------

_tentativas = {}
_trava_tentativas = threading.Lock()


def _bloqueado(ip):
    agora = time.monotonic()
    with _trava_tentativas:
        recentes = [t for t in _tentativas.get(ip, []) if agora - t < JANELA_BLOQUEIO]
        _tentativas[ip] = recentes
        return len(recentes) >= MAX_TENTATIVAS


def _registrar_falha(ip):
    with _trava_tentativas:
        _tentativas.setdefault(ip, []).append(time.monotonic())


def _limpar_falhas(ip):
    with _trava_tentativas:
        _tentativas.pop(ip, None)


# ---------------------------------------------------------------------------
# Sessão, CSRF e decoradores
# ---------------------------------------------------------------------------

def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def _carregar_usuario():
    g.usuario = None
    usuario_id = session.get("usuario_id")
    if usuario_id is None:
        return
    linha = db.obter().execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if linha and hmac.compare_digest(linha["token_sessao"], session.get("token", "")):
        g.usuario = linha
    else:
        session.clear()


def csrf_isento(funcao):
    """Para rotas chamadas pelas TVs, que se identificam pelo código da tela."""
    funcao.csrf_isento = True
    return funcao


def _verificar_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    rota = current_app.view_functions.get(request.endpoint)
    if getattr(rota, "csrf_isento", False):
        return
    enviado = request.form.get("csrf_token", "")
    esperado = session.get("csrf", "")
    if not esperado or not hmac.compare_digest(enviado, esperado):
        log.warning("CSRF inválido em %s vindo de %s", request.path, request.remote_addr)
        abort(400)


def login_obrigatorio(papel=None):
    def decorador(funcao):
        @wraps(funcao)
        def verificar(*args, **kwargs):
            if g.usuario is None:
                if not existe_usuario(db.obter()):
                    return redirect(url_for("auth.configurar"))
                return redirect(url_for("auth.login", proximo=request.full_path.rstrip("?")))
            if papel and g.usuario["papel"] != papel:
                abort(403)
            return funcao(*args, **kwargs)

        return verificar

    return decorador


def _destino_seguro(proximo):
    # Evita redirecionar para outro site (open redirect).
    if proximo and proximo.startswith("/") and not proximo.startswith("//") and "\\" not in proximo:
        return proximo
    return url_for("painel.lista")


def _entrar(usuario):
    session.clear()
    session.permanent = True
    session["usuario_id"] = usuario["id"]
    session["token"] = usuario["token_sessao"]


def registrar(app):
    app.register_blueprint(bp)
    app.before_request(_verificar_csrf)
    app.before_request(_carregar_usuario)
    app.jinja_env.globals["csrf_token"] = token_csrf
    app.jinja_env.globals["PAPEIS"] = PAPEIS

    @app.after_request
    def nao_guardar_paginas_restritas(resposta):
        if getattr(g, "usuario", None) is not None and resposta.mimetype == "text/html":
            resposta.headers["Cache-Control"] = "no-store"
        return resposta


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

@bp.route("/configurar", methods=["GET", "POST"])
def configurar():
    """Primeiro acesso: cria o administrador. Some depois que existe um usuário."""
    conexao = db.obter()
    if existe_usuario(conexao):
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        usuario = request.form.get("usuario", "")
        senha = request.form.get("senha", "")
        if senha != request.form.get("confirmacao", ""):
            flash("As senhas não conferem.", "erro")
        else:
            try:
                criar_usuario(conexao, usuario, senha, "admin")
            except ErroUsuario as erro:
                flash(str(erro), "erro")
            else:
                novo = conexao.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario.strip(),)).fetchone()
                _entrar(novo)
                log.info("Administrador inicial “%s” criado (IP %s)", novo["usuario"], request.remote_addr)
                flash("Tudo pronto! Agora envie suas propagandas.", "ok")
                return redirect(url_for("painel.lista"))
    return render_template("configurar.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    conexao = db.obter()
    if not existe_usuario(conexao):
        return redirect(url_for("auth.configurar"))
    if g.usuario is not None:
        return redirect(url_for("painel.lista"))

    if request.method == "POST":
        ip = request.remote_addr or "?"
        usuario = request.form.get("usuario", "").strip()
        if _bloqueado(ip):
            log.warning("Login bloqueado por excesso de tentativas (IP %s)", ip)
            flash("Muitas tentativas erradas. Aguarde 15 minutos e tente de novo.", "erro")
            return render_template("login.html", usuario=usuario), 429

        linha = conexao.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
        if linha and check_password_hash(linha["senha_hash"], request.form.get("senha", "")):
            _limpar_falhas(ip)
            _entrar(linha)
            log.info("Login de “%s” (IP %s)", linha["usuario"], ip)
            return redirect(_destino_seguro(request.args.get("proximo")))

        _registrar_falha(ip)
        log.warning("Senha errada para “%s” (IP %s)", usuario, ip)
        flash("Usuário ou senha incorretos.", "erro")
        return render_template("login.html", usuario=usuario), 401

    return render_template("login.html", usuario="")


@bp.route("/sair", methods=["POST"])
def sair():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/senha", methods=["GET", "POST"])
@login_obrigatorio()
def minha_senha():
    if request.method == "POST":
        atual = request.form.get("atual", "")
        nova = request.form.get("nova", "")
        if not check_password_hash(g.usuario["senha_hash"], atual):
            flash("A senha atual está incorreta.", "erro")
        elif nova != request.form.get("confirmacao", ""):
            flash("As senhas novas não conferem.", "erro")
        else:
            try:
                trocar_senha(db.obter(), g.usuario["id"], nova)
            except ErroUsuario as erro:
                flash(str(erro), "erro")
            else:
                linha = db.obter().execute("SELECT * FROM usuarios WHERE id = ?", (g.usuario["id"],)).fetchone()
                _entrar(linha)  # mantém este aparelho conectado
                log.info("“%s” trocou a própria senha", linha["usuario"])
                flash("Senha alterada. Os outros aparelhos foram desconectados.", "ok")
                return redirect(url_for("painel.lista"))
    return render_template("senha.html")


@bp.route("/usuarios")
@login_obrigatorio("admin")
def usuarios():
    linhas = db.obter().execute("SELECT * FROM usuarios ORDER BY usuario").fetchall()
    return render_template("usuarios.html", usuarios=linhas)


@bp.route("/usuarios/novo", methods=["POST"])
@login_obrigatorio("admin")
def novo_usuario():
    try:
        criar_usuario(
            db.obter(),
            request.form.get("usuario", ""),
            request.form.get("senha", ""),
            request.form.get("papel", "editor"),
        )
    except ErroUsuario as erro:
        flash(str(erro), "erro")
    else:
        log.info("“%s” criou o usuário “%s”", g.usuario["usuario"], request.form.get("usuario", "").strip())
        flash("Usuário criado.", "ok")
    return redirect(url_for("auth.usuarios"))


@bp.route("/usuarios/<int:usuario_id>/excluir", methods=["POST"])
@login_obrigatorio("admin")
def excluir_usuario(usuario_id):
    conexao = db.obter()
    alvo = conexao.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if alvo is None:
        abort(404)
    if alvo["id"] == g.usuario["id"]:
        flash("Você não pode excluir o próprio usuário.", "erro")
    else:
        with conexao:
            conexao.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
        log.info("“%s” excluiu o usuário “%s”", g.usuario["usuario"], alvo["usuario"])
        flash("Usuário excluído.", "ok")
    return redirect(url_for("auth.usuarios"))
