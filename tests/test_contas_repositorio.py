"""Contas no SQLite deste painel, com o hash de senha real: o nome é único no sistema todo e o login não pede a loja."""

import pytest

from propagandas import db
from src.domain.contas import CredenciaisInvalidas, ErroUsuario, ServicoDeContas
from src.infrastructure.senhas import SenhasWerkzeug
from src.infrastructure.sqlite import RepositorioDeContasSQLite


@pytest.fixture
def contas(app):
    conexao = db.conectar(app.config["BANCO"])
    with conexao:
        conexao.execute("INSERT INTO empresas (id, nome) VALUES (2, 'Lanchonete')")
        conexao.execute("INSERT INTO empresas (id, nome) VALUES (3, 'Padaria')")
    yield ServicoDeContas(RepositorioDeContasSQLite(conexao), SenhasWerkzeug()), conexao
    conexao.close()


def test_nome_unico_e_login_sem_loja(contas):
    servico, conexao = contas
    joao = servico.criar_na_loja(2, {"painel"}, "joao", "senha-do-joao", "editor")
    with pytest.raises(ErroUsuario, match="já existe"):
        servico.criar(3, "JOAO", "outra-senha-123", "editor")          # em outra loja também não pode
    with pytest.raises(ErroUsuario, match="papel"):
        servico.criar_na_loja(2, {"painel"}, "maria", "senha-da-maria", "garcom")   # sem a Comanda
    assert servico.entrar("joao", "senha-do-joao", None, "1.1.1.1").id == joao
    with pytest.raises(CredenciaisInvalidas):
        servico.entrar("joao", "errada", None, "1.1.1.1")
    senha_hash = conexao.execute("SELECT senha_hash FROM usuarios WHERE id = ?", (joao,)).fetchone()[0]
    assert "senha-do-joao" not in senha_hash
    alvo, mudancas = servico.editar(2, 999, joao, "admin", "", {"painel"})
    assert alvo.usuario == "joao" and servico.conta(joao).papel == "admin" and mudancas
