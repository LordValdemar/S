"""Acesso ao banco SQLite e migrações do esquema."""

import os
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
    # 3 - multiempresa (cada cliente vê só os próprios dados), 2FA e limites de plano.
    # As tabelas são reconstruídas para que empresa_id seja obrigatório e SEM valor
    # padrão: esquecer a empresa num INSERT dá erro em vez de vazar dados.
    """
    CREATE TABLE empresas (
        id                 INTEGER PRIMARY KEY,
        nome               TEXT    NOT NULL,
        ativa              INTEGER NOT NULL DEFAULT 1,
        limite_telas       INTEGER,            -- NULL = sem limite
        limite_mb          INTEGER,            -- armazenamento; NULL = sem limite
        alerta_emails      TEXT    NOT NULL DEFAULT '',
        alerta_webhook     TEXT    NOT NULL DEFAULT '',
        criado_em          TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    INSERT INTO empresas (id, nome) VALUES (1, 'Minha empresa');

    CREATE TABLE usuarios_novo (
        id            INTEGER PRIMARY KEY,
        empresa_id    INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
        usuario       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
        senha_hash    TEXT    NOT NULL,
        papel         TEXT    NOT NULL CHECK (papel IN ('admin', 'editor')),
        plataforma    INTEGER NOT NULL DEFAULT 0,   -- administra todas as empresas
        token_sessao  TEXT    NOT NULL,
        totp_segredo  TEXT,                          -- NULL = 2FA desligada
        totp_pendente TEXT,                          -- segredo gerado, aguardando confirmação
        totp_ultimo   INTEGER NOT NULL DEFAULT 0,    -- impede reuso do mesmo código
        criado_em     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    -- Quem já administrava o sistema vira administrador da plataforma.
    INSERT INTO usuarios_novo (id, empresa_id, usuario, senha_hash, papel, plataforma, token_sessao, criado_em)
        SELECT id, 1, usuario, senha_hash, papel, papel = 'admin', token_sessao, criado_em FROM usuarios;
    DROP TABLE usuarios;
    ALTER TABLE usuarios_novo RENAME TO usuarios;
    CREATE INDEX usuarios_empresa ON usuarios(empresa_id);

    CREATE TABLE grupos_novo (
        id          INTEGER PRIMARY KEY,
        empresa_id  INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
        nome        TEXT    NOT NULL COLLATE NOCASE,
        UNIQUE (empresa_id, nome)
    );
    INSERT INTO grupos_novo (id, empresa_id, nome) SELECT id, 1, nome FROM grupos;
    DROP TABLE grupos;
    ALTER TABLE grupos_novo RENAME TO grupos;

    CREATE TABLE telas_novo (
        id              INTEGER PRIMARY KEY,
        empresa_id      INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
        nome            TEXT    NOT NULL,
        codigo          TEXT    NOT NULL UNIQUE,
        grupo_id        INTEGER REFERENCES grupos(id) ON DELETE SET NULL,
        letreiro        TEXT,
        ultimo_contato  TEXT,
        ultimo_ip       TEXT,
        navegador       TEXT,
        exibindo        TEXT,
        alerta_offline  INTEGER NOT NULL DEFAULT 0,
        criado_em       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    INSERT INTO telas_novo
        SELECT id, 1, nome, codigo, grupo_id, letreiro, ultimo_contato, ultimo_ip, navegador,
               exibindo, alerta_offline, criado_em
        FROM telas;
    DROP TABLE telas;
    ALTER TABLE telas_novo RENAME TO telas;
    CREATE INDEX telas_empresa ON telas(empresa_id);

    CREATE TABLE propagandas_novo (
        id           INTEGER PRIMARY KEY,
        empresa_id   INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
        nome         TEXT    NOT NULL,
        arquivo      TEXT    NOT NULL UNIQUE,
        tipo         TEXT    NOT NULL CHECK (tipo IN ('imagem', 'video')),
        tamanho      INTEGER NOT NULL DEFAULT 0,   -- bytes, para o limite de armazenamento
        duracao      INTEGER NOT NULL CHECK (duracao BETWEEN 1 AND 3600),
        ativo        INTEGER NOT NULL DEFAULT 1,
        inicio       TEXT,
        fim          TEXT,
        dias_semana  TEXT    NOT NULL DEFAULT '0123456',
        hora_inicio  TEXT,
        hora_fim     TEXT,
        para_todas   INTEGER NOT NULL DEFAULT 1,
        posicao      INTEGER NOT NULL,
        criado_em    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    INSERT INTO propagandas_novo (id, empresa_id, nome, arquivo, tipo, duracao, ativo, inicio, fim,
                                  dias_semana, hora_inicio, hora_fim, para_todas, posicao, criado_em)
        SELECT id, 1, nome, arquivo, tipo, duracao, ativo, inicio, fim,
               dias_semana, hora_inicio, hora_fim, para_todas, posicao, criado_em
        FROM propagandas;
    DROP TABLE propagandas;
    ALTER TABLE propagandas_novo RENAME TO propagandas;
    CREATE INDEX propagandas_empresa ON propagandas(empresa_id, posicao);

    CREATE TABLE configuracoes_novo (
        empresa_id  INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
        chave       TEXT    NOT NULL,
        valor       TEXT    NOT NULL,
        PRIMARY KEY (empresa_id, chave)
    );
    INSERT INTO configuracoes_novo SELECT 1, chave, valor FROM configuracoes;
    DROP TABLE configuracoes;
    ALTER TABLE configuracoes_novo RENAME TO configuracoes;

    CREATE TABLE exibicoes_novo (
        id               INTEGER PRIMARY KEY,
        empresa_id       INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
        tela_id          INTEGER REFERENCES telas(id) ON DELETE SET NULL,
        propaganda_id    INTEGER NOT NULL,
        propaganda_nome  TEXT    NOT NULL,
        exibido_em       TEXT    NOT NULL,
        duracao          REAL    NOT NULL,
        UNIQUE (tela_id, propaganda_id, exibido_em)
    );
    INSERT INTO exibicoes_novo
        SELECT id, 1, tela_id, propaganda_id, propaganda_nome, exibido_em, duracao FROM exibicoes;
    DROP TABLE exibicoes;
    ALTER TABLE exibicoes_novo RENAME TO exibicoes;
    CREATE INDEX exibicoes_empresa_data ON exibicoes(empresa_id, exibido_em);
    CREATE INDEX exibicoes_data ON exibicoes(exibido_em);
    """,
    # 4 - planos com preço e cobrança automática (Asaas)
    """
    CREATE TABLE planos (
        id              INTEGER PRIMARY KEY,
        nome            TEXT    NOT NULL UNIQUE COLLATE NOCASE,
        preco_centavos  INTEGER NOT NULL CHECK (preco_centavos >= 0),
        limite_telas    INTEGER,
        limite_mb       INTEGER,
        ativo           INTEGER NOT NULL DEFAULT 1
    );

    ALTER TABLE empresas ADD COLUMN plano_id INTEGER REFERENCES planos(id) ON DELETE SET NULL;
    ALTER TABLE empresas ADD COLUMN documento TEXT NOT NULL DEFAULT '';        -- CPF ou CNPJ (só números)
    ALTER TABLE empresas ADD COLUMN email_cobranca TEXT NOT NULL DEFAULT '';
    ALTER TABLE empresas ADD COLUMN motivo_suspensao TEXT;                     -- 'manual' ou 'inadimplencia'
    ALTER TABLE empresas ADD COLUMN cobranca_automatica INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE empresas ADD COLUMN asaas_cliente_id TEXT;
    ALTER TABLE empresas ADD COLUMN asaas_assinatura_id TEXT;
    UPDATE empresas SET motivo_suspensao = 'manual' WHERE ativa = 0;
    CREATE UNIQUE INDEX empresas_assinatura ON empresas(asaas_assinatura_id) WHERE asaas_assinatura_id IS NOT NULL;

    CREATE TABLE faturas (
        id              INTEGER PRIMARY KEY,
        empresa_id      INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
        asaas_id        TEXT    NOT NULL UNIQUE,
        valor_centavos  INTEGER NOT NULL,
        vencimento      TEXT    NOT NULL,           -- AAAA-MM-DD
        status          TEXT    NOT NULL,           -- status do Asaas (PENDING, RECEIVED, OVERDUE...)
        link            TEXT,                       -- página de pagamento (PIX, boleto ou cartão)
        pago_em         TEXT,
        atualizado_em   TEXT    NOT NULL
    );
    CREATE INDEX faturas_empresa ON faturas(empresa_id, vencimento);

    -- Eventos de webhook já processados (o Asaas pode reenviar o mesmo evento).
    CREATE TABLE webhook_eventos (
        id           TEXT PRIMARY KEY,
        recebido_em  TEXT NOT NULL
    );
    """,
    # 5 - letreiro próprio por propaganda: NULL = usa o geral (ou o da tela), '' = sem letreiro.
    """
    ALTER TABLE propagandas ADD COLUMN letreiro TEXT;
    """,
    # 6 - pareamento: cada tela funciona só no aparelho conectado a ela (pelo QR code da
    # página /tela). Guarda o hash do "crachá" (cookie secreto) do aparelho.
    # aceita_link = 1 só nas telas que já existiam: a TV que já usa o endereço se conecta
    # sozinha no próximo contato, uma vez. Telas novas só se conectam pelo QR code.
    """
    ALTER TABLE telas ADD COLUMN aparelho_hash TEXT;
    ALTER TABLE telas ADD COLUMN pareada_em TEXT;
    ALTER TABLE telas ADD COLUMN aceita_link INTEGER NOT NULL DEFAULT 1;

    -- Pedido de conexão feito por uma TV na página /tela: o código curto vai no QR code;
    -- o segredo fica só no cookie da TV (aqui, só o hash).
    CREATE TABLE pareamentos (
        id            INTEGER PRIMARY KEY,
        codigo        TEXT    NOT NULL UNIQUE,
        segredo_hash  TEXT    NOT NULL UNIQUE,
        criado_em     TEXT    NOT NULL,
        tela_id       INTEGER REFERENCES telas(id) ON DELETE CASCADE
    );
    """,
    # 7 - a TV avisa quando a janela é fechada: fica offline na hora, sem esperar os 3 minutos.
    """
    ALTER TABLE telas ADD COLUMN fechada_em TEXT;
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
        if versao >= len(MIGRACOES):
            return
        # Reconstruir tabelas exige desligar as chaves estrangeiras durante a
        # migração (procedimento oficial do SQLite); a integridade é conferida no fim.
        conexao.execute("PRAGMA foreign_keys = OFF")
        for numero in range(versao + 1, len(MIGRACOES) + 1):
            conexao.executescript(
                f"BEGIN;\n{MIGRACOES[numero - 1]}\nPRAGMA user_version = {numero};\nCOMMIT;"
            )
        problemas = conexao.execute("PRAGMA foreign_key_check").fetchall()
        if problemas:
            raise RuntimeError(f"Migração deixou referências inválidas: {[tuple(p) for p in problemas]}")
        conexao.execute("PRAGMA foreign_keys = ON")
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


def ler_config(empresa_id, chave, padrao=""):
    linha = obter().execute(
        "SELECT valor FROM configuracoes WHERE empresa_id = ? AND chave = ?", (empresa_id, chave)
    ).fetchone()
    return linha["valor"] if linha else padrao


def gravar_config(empresa_id, chave, valor):
    conexao = obter()
    with conexao:
        conexao.execute(
            "INSERT INTO configuracoes (empresa_id, chave, valor) VALUES (?, ?, ?) "
            "ON CONFLICT(empresa_id, chave) DO UPDATE SET valor = excluded.valor",
            (empresa_id, chave, valor),
        )


def preencher_tamanhos(caminho_banco, pasta_midia):
    """Calcula o tamanho dos arquivos enviados antes da versão com limite de armazenamento."""
    conexao = conectar(caminho_banco)
    try:
        pendentes = conexao.execute("SELECT id, arquivo FROM propagandas WHERE tamanho = 0").fetchall()
        with conexao:
            for linha in pendentes:
                caminho = os.path.join(pasta_midia, linha["arquivo"])
                if os.path.exists(caminho):
                    conexao.execute(
                        "UPDATE propagandas SET tamanho = ? WHERE id = ?", (os.path.getsize(caminho), linha["id"])
                    )
    finally:
        conexao.close()
