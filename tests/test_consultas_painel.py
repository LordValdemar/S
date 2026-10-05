"""Consultas das telas deste painel (cópia da plataforma) no SQLite daqui: isolamento entre lojas."""

import pytest

from propagandas import db
from src.infrastructure.sqlite import ConsultasDoPainel


@pytest.fixture
def conexao(app):
    conexao = db.conectar(app.config["BANCO"])
    with conexao:
        conexao.execute("INSERT INTO empresas (id, nome) VALUES (2, 'Outra')")
        conexao.executemany("INSERT INTO grupos (id, empresa_id, nome) VALUES (?, ?, ?)", [(7, 1, "SP"), (8, 2, "RJ")])
        conexao.executemany("INSERT INTO telas (id, empresa_id, nome, codigo, grupo_id) VALUES (?, ?, ?, ?, ?)",
                            [(10, 1, "Vitrine", "v-1", 7), (11, 1, "Balcão", "b-1", None), (20, 2, "Da outra", "o-1", 8)])
        conexao.executemany("INSERT INTO propagandas (id, empresa_id, nome, arquivo, tipo, duracao, posicao) "
                            "VALUES (?, ?, ?, ?, 'imagem', 10, ?)", [(1, 1, "a", "a.png", 1), (2, 2, "b", "b.png", 1)])
        conexao.executemany("INSERT INTO propaganda_destinos (propaganda_id, tela_id, grupo_id) VALUES (?, ?, ?)",
                            [(1, 11, None), (1, None, 7), (2, 20, None)])
    yield conexao
    conexao.close()


def test_painel(conexao):
    loja, outra = ConsultasDoPainel(conexao, 1), ConsultasDoPainel(conexao, 2)
    assert [t["nome"] for t in loja.telas_para_escolher()] == ["Balcão", "Vitrine"]
    assert [(t["nome"], t["grupo_nome"]) for t in loja.telas()] == [("Balcão", None), ("Vitrine", "SP")]
    assert [(g["nome"], g["total"]) for g in loja.grupos_com_total()] == [("SP", 1)]
    assert [g["nome"] for g in outra.grupos_para_escolher()] == ["RJ"]
    assert loja.destinos_por_propaganda() == {1: {"telas": {11}, "grupos": {7}, "nomes": ["Balcão", "Grupo SP"]}}
    assert outra.destinos_por_propaganda() == {2: {"telas": {20}, "grupos": set(), "nomes": ["Da outra"]}}

