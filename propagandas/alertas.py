"""Alertas de tela offline por e-mail e/ou webhook (Slack, Teams, Discord, Google Chat...)."""

import json
import logging
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage

from flask import current_app

from . import agenda, db

log = logging.getLogger("propagandas.alertas")

ONLINE_SEGUNDOS = 180  # a TV manda sinal de vida a cada minuto


def canais_configurados(config):
    canais = []
    if config["SMTP_HOST"] and config["ALERTA_EMAILS"]:
        canais.append("e-mail")
    if config["ALERTA_WEBHOOK"]:
        canais.append("webhook")
    return canais


def _enviar_email(config, assunto, mensagem):
    destinatarios = [e.strip() for e in config["ALERTA_EMAILS"].split(",") if e.strip()]
    email = EmailMessage()
    email["Subject"] = assunto
    email["From"] = config["SMTP_REMETENTE"] or config["SMTP_USUARIO"]
    email["To"] = ", ".join(destinatarios)
    email.set_content(mensagem)
    contexto = ssl.create_default_context()
    if config["SMTP_PORTA"] == 465:
        servidor = smtplib.SMTP_SSL(config["SMTP_HOST"], 465, timeout=20, context=contexto)
    else:
        servidor = smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORTA"], timeout=20)
        servidor.starttls(context=contexto)
    with servidor:
        if config["SMTP_USUARIO"]:
            servidor.login(config["SMTP_USUARIO"], config["SMTP_SENHA"])
        servidor.send_message(email)


def _enviar_webhook(config, mensagem):
    # "text" é o formato do Slack/Teams/Google Chat; "content" é o do Discord.
    corpo = json.dumps({"text": mensagem, "content": mensagem}).encode()
    pedido = urllib.request.Request(
        config["ALERTA_WEBHOOK"], data=corpo, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(pedido, timeout=20) as resposta:  # noqa: S310 (URL definida pelo administrador)
        resposta.read()


def enviar_alerta(mensagem, config=None):
    """Envia por todos os canais configurados. Retorna a lista de erros (vazia = tudo certo)."""
    config = config or current_app.config
    log.warning("ALERTA: %s", mensagem)
    erros = []
    if config["SMTP_HOST"] and config["ALERTA_EMAILS"]:
        try:
            _enviar_email(config, "Painel de Propagandas: " + mensagem[:80], mensagem)
        except Exception as erro:
            log.exception("Falha ao enviar alerta por e-mail")
            erros.append(f"e-mail: {erro}")
    if config["ALERTA_WEBHOOK"]:
        try:
            _enviar_webhook(config, mensagem)
        except Exception as erro:
            log.exception("Falha ao enviar alerta por webhook")
            erros.append(f"webhook: {erro}")
    return erros


def esta_online(tela):
    if not tela["ultimo_contato"]:
        return False
    segundos = (agenda.agora_utc() - agenda.de_texto_utc(tela["ultimo_contato"])).total_seconds()
    return segundos < ONLINE_SEGUNDOS


def verificar_telas():
    """Avisa uma vez quando uma tela cai e outra vez quando ela volta."""
    config = current_app.config
    limite = config["ALERTA_OFFLINE_MIN"] * 60
    conexao = db.obter()
    agora = agenda.agora_utc()
    for tela in conexao.execute("SELECT * FROM telas WHERE ultimo_contato IS NOT NULL").fetchall():
        sem_contato = (agora - agenda.de_texto_utc(tela["ultimo_contato"])).total_seconds()
        if sem_contato > limite and not tela["alerta_offline"]:
            enviar_alerta(
                f"⚠️ A tela “{tela['nome']}” está sem comunicação desde "
                f"{agenda.local_formatado(tela['ultimo_contato'])}."
            )
            novo_estado = 1
        elif sem_contato <= limite and tela["alerta_offline"]:
            enviar_alerta(f"✅ A tela “{tela['nome']}” voltou a funcionar.")
            novo_estado = 0
        else:
            continue
        with conexao:
            conexao.execute("UPDATE telas SET alerta_offline = ? WHERE id = ?", (novo_estado, tela["id"]))
