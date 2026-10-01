"""Cliente da API v3 do Asaas (https://docs.asaas.com).

Só a biblioteca padrão do Python. As chamadas passam por `_enviar`, que os
testes substituem por um Asaas falso.
"""

import json
import logging
import urllib.error
import urllib.request
from urllib.parse import urlencode

from flask import current_app

log = logging.getLogger("propagandas.asaas")

URLS = {
    "sandbox": "https://api-sandbox.asaas.com/v3",
    "producao": "https://api.asaas.com/v3",
}
USER_AGENT = "PainelPropagandas/1.0"  # o Asaas exige o cabeçalho User-Agent


class ErroAsaas(Exception):
    """Erro devolvido pelo Asaas (mensagem pronta para mostrar na tela)."""


def configurado(config=None):
    config = config or current_app.config
    return bool(config["ASAAS_API_KEY"])


def _enviar(metodo, url, chave, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    pedido = urllib.request.Request(
        url,
        data=dados,
        method=metodo,
        headers={
            "access_token": chave,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            return json.loads(resposta.read() or b"{}")
    except urllib.error.HTTPError as erro:
        try:
            detalhes = json.loads(erro.read() or b"{}")
            mensagem = "; ".join(e.get("description", "") for e in detalhes.get("errors", [])) or str(erro)
        except ValueError:
            mensagem = str(erro)
        raise ErroAsaas(mensagem) from erro
    except urllib.error.URLError as erro:
        raise ErroAsaas(f"não foi possível falar com o Asaas ({erro.reason})") from erro


def chamar(metodo, caminho, corpo=None, parametros=None):
    config = current_app.config
    if not configurado(config):
        raise ErroAsaas("a integração com o Asaas não está configurada (ASAAS_API_KEY)")
    url = (config["ASAAS_URL"] or URLS[config["ASAAS_AMBIENTE"]]) + caminho
    if parametros:
        url += "?" + urlencode(parametros)
    log.info("Asaas %s %s", metodo, caminho)
    return _enviar(metodo, url, config["ASAAS_API_KEY"], corpo)


# ---------------------------------------------------------------------------
# Operações usadas pelo sistema
# ---------------------------------------------------------------------------

def criar_cliente(nome, documento, email, referencia):
    return chamar("POST", "/customers", {
        "name": nome,
        "cpfCnpj": documento,
        "email": email or None,
        "externalReference": referencia,
        "notificationDisabled": False,  # o Asaas avisa o cliente sobre faturas
    })


def criar_assinatura(cliente_id, valor_centavos, primeiro_vencimento, descricao, referencia):
    return chamar("POST", "/subscriptions", {
        "customer": cliente_id,
        "billingType": "UNDEFINED",  # o cliente escolhe PIX, boleto ou cartão na fatura
        "value": valor_centavos / 100,
        "nextDueDate": primeiro_vencimento,
        "cycle": "MONTHLY",
        "description": descricao,
        "externalReference": referencia,
    })


def atualizar_assinatura(assinatura_id, valor_centavos, descricao):
    return chamar("PUT", f"/subscriptions/{assinatura_id}", {
        "value": valor_centavos / 100,
        "description": descricao,
        "updatePendingPayments": True,  # aplica também às faturas ainda não pagas
    })


def cancelar_assinatura(assinatura_id):
    return chamar("DELETE", f"/subscriptions/{assinatura_id}")


def faturas_da_assinatura(assinatura_id):
    resposta = chamar("GET", f"/subscriptions/{assinatura_id}/payments", parametros={"limit": 100})
    return resposta.get("data", [])
