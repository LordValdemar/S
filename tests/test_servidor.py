"""Testa o servidor de produção (Waitress) de verdade, atrás de um proxy simulado."""
import http.client
import os
import sys
import threading

import pytest
from waitress.server import create_server

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import servidor  # noqa: E402
from propagandas import create_app  # noqa: E402


@pytest.fixture
def servidor_real(tmp_path):
    """Sobe o Waitress numa porta livre e devolve uma função para fazer pedidos."""
    def subir(atras_de_proxy):
        app = create_app({"PASTA_DADOS": str(tmp_path), "TESTING": True, "SECRET_KEY": "x",
                          "ATRAS_DE_PROXY": atras_de_proxy})

        @app.route("/_quem_sou_eu")
        def quem_sou_eu():
            from flask import request, url_for
            return {"ip": request.remote_addr, "url": url_for("exibicao.saude", _external=True)}

        servidor_wsgi = create_server(app, host="127.0.0.1", port=0, **servidor.opcoes_waitress(app.config))
        threading.Thread(target=servidor_wsgi.run, daemon=True).start()
        porta = servidor_wsgi.effective_port

        def pedir(cabecalhos):
            conexao = http.client.HTTPConnection("127.0.0.1", porta, timeout=5)
            conexao.request("GET", "/_quem_sou_eu", headers={"Host": "painel.exemplo.com.br", **cabecalhos})
            import json
            return json.loads(conexao.getresponse().read())

        subir.servidores.append(servidor_wsgi)
        return pedir

    subir.servidores = []
    yield subir
    for s in subir.servidores:
        s.close()


def test_atras_do_proxy_usa_ip_e_https_reais(servidor_real):
    pedir = servidor_real(atras_de_proxy=True)
    resposta = pedir({"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"})
    assert resposta["ip"] == "203.0.113.7"
    assert resposta["url"] == "https://painel.exemplo.com.br/saude"


def test_sem_proxy_ignora_cabecalhos_falsificados(servidor_real):
    pedir = servidor_real(atras_de_proxy=False)
    resposta = pedir({"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"})
    assert resposta["ip"] == "127.0.0.1"
    assert resposta["url"].startswith("http://")


def test_proxy_confiavel_e_so_o_local(monkeypatch, servidor_real):
    """Se o proxy configurado é outro endereço, um cliente direto não consegue fingir outro IP."""
    monkeypatch.setenv("PROXY_CONFIAVEL", "10.9.9.9")
    pedir = servidor_real(atras_de_proxy=True)
    resposta = pedir({"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"})
    assert resposta["ip"] == "127.0.0.1"
    assert resposta["url"].startswith("http://")
