"""Relatório de exibições no SQLite deste painel (regras do núcleo): isolamento entre lojas e dia local."""

import pytest

from propagandas import db
from src.domain.relatorios import RelatorioDeExibicoes
from src.infrastructure.sqlite import RepositorioDeExibicoesSQLite

DIA = ("2000-01-01 00:00:00", "2100-01-01 00:00:00")


@pytest.fixture
def conexao(app):
    conexao = db.conectar(app.config["BANCO"])
    with conexao:
        conexao.execute("INSERT INTO empresas (id, nome) VALUES (2, 'Outra loja')")
        conexao.execute("INSERT INTO telas (id, empresa_id, nome, codigo) VALUES (5, 1, 'Balcão', 'balcao-x')")
        conexao.executemany(
            "INSERT INTO exibicoes (empresa_id, tela_id, propaganda_id, propaganda_nome, exibido_em, duracao) VALUES (?, ?, ?, ?, ?, ?)",
            [(1, 5, 9, "Café", "2026-10-04 02:30:00", 10), (1, 5, 9, "Café", "2026-10-04 12:00:00", 10),
             (2, None, 9, "Da outra", "2026-10-04 12:00:00", 10)])
    yield conexao
    conexao.close()


def test_exibicoes_por_dia_local(conexao):
    relatorio = RelatorioDeExibicoes(RepositorioDeExibicoesSQLite(conexao, 1))
    resumo = relatorio.resumo(*DIA, None)
    assert [(p.nome, p.excluida, p.exibicoes, p.telas) for p in resumo.por_propaganda] == [("Café", True, 2, 1)]
    assert (resumo.total_exibicoes, resumo.total_tempo) == (2, 20)
    linhas = relatorio.planilha(*DIA, None, ajuste_minutos=-180)    # 02:30 UTC = 23:30 do dia 3 em São Paulo
    assert [linha[0] for linha in linhas[1:]] == ["03/10/2026", "04/10/2026"]
    assert relatorio.resumo(*DIA, tela_id=99).total_exibicoes == 0
