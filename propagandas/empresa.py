"""Configurações da empresa, uso do plano e exportação dos dados (portabilidade, LGPD)."""

import csv
import io
import json
import logging
import os
import tempfile
import zipfile

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, send_file, url_for

from src.domain.empresas import CadastroInvalido, ler_emails
from src.domain.empresas.cadastro import NOME_MAX
from src.domain.empresas.servico import WEBHOOK_MAX
from src.infrastructure.alertas import motivo_para_recusar
from src.infrastructure.sqlite import RepositorioDaEmpresaSQLite

from . import agenda, alertas, db, planos
from .auth import login_obrigatorio

bp = Blueprint("empresa", __name__)
log = logging.getLogger("propagandas.empresa")


@bp.route("/empresa", methods=["GET", "POST"])
@login_obrigatorio("admin")
def configuracoes():
    conexao = db.obter()
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()[:NOME_MAX]
        webhook = request.form.get("alerta_webhook", "").strip()[:WEBHOOK_MAX]
        try:
            emails = ler_emails(request.form.get("alerta_emails"))
        except CadastroInvalido as erro:
            emails, erro_emails = [], str(erro)
        else:
            erro_emails = None
        if not nome:
            flash("Informe o nome da empresa.", "erro")
        elif erro_emails:
            flash(erro_emails, "erro")
        elif webhook and (erro_webhook := motivo_para_recusar(webhook)):
            flash(f"Webhook recusado: {erro_webhook}.", "erro")
        else:
            RepositorioDaEmpresaSQLite(conexao).gravar_configuracoes(g.empresa_id, nome, ", ".join(emails), webhook)
            log.info("“%s” alterou as configurações da empresa %s", g.usuario["usuario"], g.empresa_id)
            flash("Configurações salvas.", "ok")
            return redirect(url_for("empresa.configuracoes"))

    empresa = planos.empresa(conexao, g.empresa_id)
    return render_template(
        "empresa.html",
        empresa=empresa,
        uso=planos.uso(conexao, g.empresa_id),
        smtp_configurado=bool(current_app.config["SMTP_HOST"]),
        canais=alertas.canais_da_empresa(empresa, current_app.config),
        plano=planos.consultas(conexao).plano(empresa["plano_id"]),
        tem_faturas=planos.consultas(conexao).tem_faturas(g.empresa_id),
    )


@bp.route("/empresa/exportar")
@login_obrigatorio("admin")
def exportar():
    """Baixa um .zip com todos os dados da empresa e os arquivos de mídia."""
    leitura = planos.consultas()
    empresa_id = g.empresa_id
    dados = {
        "exportado_em": agenda.para_texto_utc(agenda.agora_utc()) + " UTC",
        **leitura.dados_para_exportar(empresa_id),
    }

    exibicoes = io.StringIO()
    escritor = csv.writer(exibicoes, delimiter=";")
    escritor.writerow(["exibido_em_utc", "tela_id", "propaganda_id", "propaganda", "duracao_segundos"])
    escritor.writerows(leitura.exibicoes_para_exportar(empresa_id))

    arquivo = tempfile.TemporaryFile()  # apagado sozinho quando o download termina
    with zipfile.ZipFile(arquivo, "w", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("dados.json", json.dumps(dados, ensure_ascii=False, indent=2))
        pacote.writestr("exibicoes.csv", "﻿" + exibicoes.getvalue())
        for propaganda in dados["propagandas"]:
            caminho = os.path.join(current_app.config["PASTA_MIDIA"], propaganda["arquivo"])
            if os.path.exists(caminho):
                pacote.write(caminho, "midia/" + propaganda["arquivo"], compress_type=zipfile.ZIP_STORED)
    arquivo.seek(0)
    log.info("“%s” exportou os dados da empresa %s", g.usuario["usuario"], empresa_id)
    return send_file(
        arquivo,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"dados-empresa-{empresa_id}-{agenda.agora_local():%Y%m%d}.zip",
    )
