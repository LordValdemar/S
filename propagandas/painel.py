"""Cadastro das propagandas (área restrita)."""

import logging
import os
import uuid
from datetime import date, datetime

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

from . import agenda, db, planos
from .auth import login_obrigatorio
from .midia import EXTENSOES, detectar_tipo, extensao_de

bp = Blueprint("painel", __name__)
log = logging.getLogger("propagandas.painel")

DURACAO_PADRAO = 10


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


def ler_hora(valor):
    """Aceita HH:MM; qualquer outra coisa vira vazio."""
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


def destinos_por_propaganda(conexao):
    """{propaganda_id: {"telas": {ids}, "grupos": {ids}, "nomes": [..]}}"""
    resultado = {}
    linhas = conexao.execute(
        """
        SELECT d.propaganda_id, d.tela_id, d.grupo_id, t.nome AS tela_nome, gr.nome AS grupo_nome
        FROM propaganda_destinos d
        LEFT JOIN telas t ON t.id = d.tela_id
        LEFT JOIN grupos gr ON gr.id = d.grupo_id
        JOIN propagandas p ON p.id = d.propaganda_id
        WHERE p.empresa_id = ?
        ORDER BY gr.nome, t.nome
        """,
        (g.empresa_id,),
    )
    for linha in linhas:
        destino = resultado.setdefault(linha["propaganda_id"], {"telas": set(), "grupos": set(), "nomes": []})
        if linha["grupo_id"]:
            destino["grupos"].add(linha["grupo_id"])
            destino["nomes"].append("Grupo " + linha["grupo_nome"])
        else:
            destino["telas"].add(linha["tela_id"])
            destino["nomes"].append(linha["tela_nome"])
    return resultado


def buscar(conexao, propaganda_id):
    # Sempre filtrando pela empresa: o id na URL de outra empresa dá 404.
    item = conexao.execute(
        "SELECT * FROM propagandas WHERE id = ? AND empresa_id = ?", (propaganda_id, g.empresa_id)
    ).fetchone()
    if item is None:
        abort(404)
    return item


@bp.route("/")
@login_obrigatorio()
def lista():
    conexao = db.obter()
    itens = conexao.execute(
        "SELECT * FROM propagandas WHERE empresa_id = ? ORDER BY posicao, id", (g.empresa_id,)
    ).fetchall()
    agora = agenda.agora_local()
    return render_template(
        "propagandas.html",
        itens=itens,
        situacoes={item["id"]: agenda.situacao(item, agora) for item in itens},
        destinos=destinos_por_propaganda(conexao),
        telas=conexao.execute("SELECT id, nome FROM telas WHERE empresa_id = ? ORDER BY nome", (g.empresa_id,)).fetchall(),
        grupos=conexao.execute("SELECT id, nome FROM grupos WHERE empresa_id = ? ORDER BY nome", (g.empresa_id,)).fetchall(),
        dias=agenda.DIAS,
        agenda=agenda,
        letreiro=db.ler_config(g.empresa_id, "letreiro"),
        empresa=planos.empresa(conexao, g.empresa_id),
        uso=planos.uso(conexao, g.empresa_id),
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
        tamanho = os.path.getsize(caminho)
        if not planos.cabe_no_armazenamento(conexao, g.empresa_id, tamanho):
            os.remove(caminho)
            flash(f"“{nome_original}” não foi enviado: o limite de armazenamento do seu plano foi atingido.", "erro")
            continue
        try:
            with conexao:
                conexao.execute(
                    "INSERT INTO propagandas (empresa_id, nome, arquivo, tipo, tamanho, duracao, posicao) "
                    "VALUES (?, ?, ?, ?, ?, ?, "
                    "(SELECT COALESCE(MAX(posicao), 0) + 1 FROM propagandas WHERE empresa_id = ?))",
                    (g.empresa_id, nome_original, nome_disco, tipo, tamanho, duracao, g.empresa_id),
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
    formulario = request.form
    nome = formulario.get("nome", "").strip()[:200] or item["nome"]
    inicio = ler_data(formulario.get("inicio"))
    fim = ler_data(formulario.get("fim"))
    hora_inicio = ler_hora(formulario.get("hora_inicio"))
    hora_fim = ler_hora(formulario.get("hora_fim"))
    dias = "".join(d for d in agenda.TODOS_OS_DIAS if d in formulario.getlist("dias"))
    para_todas = formulario.get("destino", "todas") == "todas"

    ids_telas = {r["id"] for r in conexao.execute("SELECT id FROM telas WHERE empresa_id = ?", (g.empresa_id,))}
    ids_grupos = {r["id"] for r in conexao.execute("SELECT id FROM grupos WHERE empresa_id = ?", (g.empresa_id,))}
    telas_escolhidas = {int(v) for v in formulario.getlist("telas") if v.isdigit()} & ids_telas
    grupos_escolhidos = {int(v) for v in formulario.getlist("grupos") if v.isdigit()} & ids_grupos

    erro = None
    if inicio and fim and fim < inicio:
        erro = "A data de término não pode ser antes da data de início."
    elif not dias:
        erro = "Escolha pelo menos um dia da semana."
    elif hora_inicio and hora_fim and hora_inicio == hora_fim:
        erro = "O horário de início e de fim não podem ser iguais."
    elif not para_todas and not telas_escolhidas and not grupos_escolhidos:
        erro = "Escolha pelo menos uma tela ou grupo (ou marque “Todas as telas”)."
    if erro:
        flash(f"“{item['nome']}”: {erro}", "erro")
        return redirect(url_for("painel.lista"))

    with conexao:
        conexao.execute(
            """
            UPDATE propagandas
            SET nome = ?, duracao = ?, ativo = ?, inicio = ?, fim = ?,
                dias_semana = ?, hora_inicio = ?, hora_fim = ?, para_todas = ?
            WHERE id = ? AND empresa_id = ?
            """,
            (
                nome,
                ler_duracao(formulario.get("duracao")),
                1 if formulario.get("ativo") == "on" else 0,
                inicio,
                fim,
                dias,
                hora_inicio,
                hora_fim,
                1 if para_todas else 0,
                propaganda_id,
                g.empresa_id,
            ),
        )
        conexao.execute("DELETE FROM propaganda_destinos WHERE propaganda_id = ?", (propaganda_id,))
        if not para_todas:
            conexao.executemany(
                "INSERT INTO propaganda_destinos (propaganda_id, tela_id) VALUES (?, ?)",
                [(propaganda_id, t) for t in sorted(telas_escolhidas)],
            )
            conexao.executemany(
                "INSERT INTO propaganda_destinos (propaganda_id, grupo_id) VALUES (?, ?)",
                [(propaganda_id, gr) for gr in sorted(grupos_escolhidos)],
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
    itens = conexao.execute(
        "SELECT id FROM propagandas WHERE empresa_id = ? ORDER BY posicao, id", (g.empresa_id,)
    ).fetchall()
    ids = [linha["id"] for linha in itens]
    if propaganda_id not in ids:
        abort(404)
    posicao = ids.index(propaganda_id)
    destino = posicao - 1 if direcao == "cima" else posicao + 1
    if 0 <= destino < len(ids):
        ids[posicao], ids[destino] = ids[destino], ids[posicao]
        with conexao:
            conexao.executemany(
                "UPDATE propagandas SET posicao = ? WHERE id = ? AND empresa_id = ?",
                [(numero, item_id, g.empresa_id) for numero, item_id in enumerate(ids, start=1)],
            )
    return redirect(url_for("painel.lista"))


@bp.route("/propaganda/<int:propaganda_id>/excluir", methods=["POST"])
@login_obrigatorio()
def excluir(propaganda_id):
    conexao = db.obter()
    item = buscar(conexao, propaganda_id)
    with conexao:
        conexao.execute("DELETE FROM propagandas WHERE id = ? AND empresa_id = ?", (propaganda_id, g.empresa_id))
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
    db.gravar_config(g.empresa_id, "letreiro", texto)
    log.info("“%s” alterou o letreiro", g.usuario["usuario"])
    flash("Letreiro salvo.", "ok")
    return redirect(url_for("painel.lista"))
