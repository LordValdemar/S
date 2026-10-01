"""
Inicia o Painel de Propagandas em modo de produção (servidor Waitress).

Também inicia as tarefas em segundo plano (monitoramento das telas,
alertas, backup diário e limpeza dos relatórios antigos).

    python servidor.py

Para desenvolvimento, com recarga automática:

    flask --app propagandas run --debug
"""

import logging
import os
import socket

from waitress import serve

from propagandas import arquivo_config, create_app
from propagandas.tarefas import iniciar_tarefas


def ip_na_rede_local():
    """IP deste computador na rede da loja (para abrir o painel de outro aparelho)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conexao:
            conexao.connect(("8.8.8.8", 80))  # UDP: nada é enviado, só escolhe a interface de rede
            return conexao.getsockname()[0]
    except OSError:
        return None


def main():
    arquivo = arquivo_config.carregar()  # configuracao.env, se existir
    app = create_app()
    iniciar_tarefas(app)  # monitoramento das telas, backup diário e limpeza

    host = os.environ.get("HOST", "0.0.0.0")
    porta = int(os.environ.get("PORTA", 5000))
    log = logging.getLogger("propagandas")
    log.info("Painel de Propagandas iniciado")
    log.info("Painel:   http://localhost:%s/", porta)
    ip = ip_na_rede_local()
    if ip and host == "0.0.0.0":
        log.info("Na rede da loja (celular, outros computadores e TVs): http://%s:%s/", ip, porta)
    log.info("Dados em: %s", app.config["PASTA_DADOS"])
    if arquivo:
        log.info("Configuração lida de: %s", arquivo)

    serve(
        app,
        host=host,
        port=porta,
        threads=int(os.environ.get("THREADS", 8)),
        ident="PainelPropagandas",
    )


if __name__ == "__main__":
    main()
