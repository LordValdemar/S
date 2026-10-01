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
