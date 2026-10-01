"""Acesso ao banco SQLite e migrações do esquema."""

import sqlite3

from flask import current_app, g

# Cada item é uma versão do banco. Para mudar o esquema, ADICIONE um novo
# item no fim da lista (nunca altere os anteriores): bancos já instalados
# rodam só as migrações que ainda não têm.
MIGRACOES = [
    # 1 - estrutura inicial
    """
    CREATE TABLE usuarios (
        id            INTEGER PRIMARY KEY,
        usuario       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
        senha_hash    TEXT    NOT NULL,
        papel         TEXT    NOT NULL CHECK (papel IN ('admin', 'editor')),
        token_sessao  TEXT    NOT NULL,
        criado_em     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE propagandas (
        id         INTEGER PRIMARY KEY,
        nome       TEXT    NOT NULL,
        arquivo    TEXT    NOT NULL UNIQUE,
        tipo       TEXT    NOT NULL CHECK (tipo IN ('imagem', 'video')),
        duracao    INTEGER NOT NULL CHECK (duracao BETWEEN 1 AND 3600),
        ativo      INTEGER NOT NULL DEFAULT 1,
        inicio     TEXT,
        fim        TEXT,
        posicao    INTEGER NOT NULL,
        criado_em  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE configuracoes (
        chave  TEXT PRIMARY KEY,
        valor  TEXT NOT NULL
    );
    """,
    # 2 - telas, grupos, agendamento e relatório de exibições
    """
    CREATE TABLE grupos (
        id    INTEGER PRIMARY KEY,
        nome  TEXT NOT NULL UNIQUE COLLATE NOCASE
    );

    CREATE TABLE telas (
        id              INTEGER PRIMARY KEY,
        nome            TEXT    NOT NULL,
        codigo          TEXT    NOT NULL UNIQUE,
        grupo_id        INTEGER REFERENCES grupos(id) ON DELETE SET NULL,
        letreiro        TEXT,                 -- NULL = usa o letreiro geral
        ultimo_contato  TEXT,                 -- UTC
        ultimo_ip       TEXT,
        navegador       TEXT,
        exibindo        TEXT,
        alerta_offline  INTEGER NOT NULL DEFAULT 0,
        criado_em       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    ALTER TABLE propagandas ADD COLUMN dias_semana TEXT NOT NULL DEFAULT '0123456';
    ALTER TABLE propagandas ADD COLUMN hora_inicio TEXT;
    ALTER TABLE propagandas ADD COLUMN hora_fim TEXT;
    ALTER TABLE propagandas ADD COLUMN para_todas INTEGER NOT NULL DEFAULT 1;

    CREATE TABLE propaganda_destinos (
        propaganda_id  INTEGER NOT NULL REFERENCES propagandas(id) ON DELETE CASCADE,
        tela_id        INTEGER REFERENCES telas(id) ON DELETE CASCADE,
        grupo_id       INTEGER REFERENCES grupos(id) ON DELETE CASCADE,
        CHECK ((tela_id IS NULL) <> (grupo_id IS NULL))
    );
    CREATE INDEX destinos_propaganda ON propaganda_destinos(propaganda_id);

    -- Sem chave estrangeira para propaganda: o relatório continua valendo
    -- mesmo depois que a propaganda é excluída.
    CREATE TABLE exibicoes (
        id               INTEGER PRIMARY KEY,
        tela_id          INTEGER REFERENCES telas(id) ON DELETE SET NULL,
        propaganda_id    INTEGER NOT NULL,
        propaganda_nome  TEXT    NOT NULL,
        exibido_em       TEXT    NOT NULL,    -- UTC
        duracao          REAL    NOT NULL,
        UNIQUE (tela_id, propaganda_id, exibido_em)
    );
    CREATE INDEX exibicoes_data ON exibicoes(exibido_em);
    """,
]


def conectar(caminho):
    conexao = sqlite3.connect(caminho, timeout=15)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def migrar(caminho):
    conexao = conectar(caminho)
    try:
        # WAL permite ler (TVs) enquanto alguém grava (painel).
        conexao.execute("PRAGMA journal_mode = WAL")
        versao = conexao.execute("PRAGMA user_version").fetchone()[0]
        for numero in range(versao + 1, len(MIGRACOES) + 1):
            conexao.executescript(
                f"BEGIN;\n{MIGRACOES[numero - 1]}\nPRAGMA user_version = {numero};\nCOMMIT;"
            )
    finally:
        conexao.close()


def obter():
    """Conexão do pedido atual (uma por requisição)."""
    if "db" not in g:
        g.db = conectar(current_app.config["BANCO"])
    return g.db


def fechar(_erro=None):
    conexao = g.pop("db", None)
    if conexao is not None:
        conexao.close()


def ler_config(chave, padrao=""):
    linha = obter().execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,)).fetchone()
    return linha["valor"] if linha else padrao


def gravar_config(chave, valor):
    conexao = obter()
    with conexao:
        conexao.execute(
            "INSERT INTO configuracoes (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (chave, valor),
        )
