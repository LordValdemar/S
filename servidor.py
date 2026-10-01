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

from waitress import serve

from propagandas import create_app
from propagandas.tarefas import iniciar_tarefas


def main():
    app = create_app()
    iniciar_tarefas(app)  # monitoramento das telas, backup diário e limpeza

    host = os.environ.get("HOST", "0.0.0.0")
    porta = int(os.environ.get("PORTA", 5000))
    log = logging.getLogger("propagandas")
    log.info("Painel de Propagandas iniciado")
    log.info("Painel:   http://localhost:%s/", porta)
    log.info("Exibição: http://localhost:%s/player", porta)
    log.info("Dados em: %s", app.config["PASTA_DADOS"])

    serve(
        app,
        host=host,
        port=porta,
        threads=int(os.environ.get("THREADS", 8)),
        ident="PainelPropagandas",
    )


if __name__ == "__main__":
    main()
