"""Limites do plano no SQLite deste painel (regras do núcleo): telas e armazenamento."""

from propagandas import db, planos


def test_limites_de_telas_e_armazenamento(app):
    conexao = db.conectar(app.config["BANCO"])
    try:
        with conexao:
            conexao.execute("UPDATE empresas SET limite_telas = 1, limite_mb = 1 WHERE id = 1")
        assert planos.pode_cadastrar_tela(conexao, 1)
        with conexao:
            conexao.execute("INSERT INTO telas (empresa_id, nome, codigo) VALUES (1, 'Balcão', 'balcao-z')")
        assert not planos.pode_cadastrar_tela(conexao, 1)
        assert planos.uso(conexao, 1).telas == 1
        assert planos.cabe_no_armazenamento(conexao, 1, planos.MB) and not planos.cabe_no_armazenamento(conexao, 1, planos.MB + 1)
        with conexao:
            conexao.execute("UPDATE empresas SET limite_telas = NULL, limite_mb = NULL WHERE id = 1")
        assert planos.pode_cadastrar_tela(conexao, 1) and planos.cabe_no_armazenamento(conexao, 1, 10**12)
    finally:
        conexao.close()
