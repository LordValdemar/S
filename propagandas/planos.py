"""Limites do plano de cada empresa (número de telas e armazenamento). As regras ficam no núcleo (src/domain/empresas)."""

from src.domain.empresas import MB
from src.infrastructure.sqlite import ConsultasDeEmpresas, RepositorioDeLimitesSQLite

from . import db

__all__ = ["MB", "cabe_no_armazenamento", "consultas", "empresa", "pode_cadastrar_tela", "uso"]


def consultas(conexao=None):
    """O que as telas leem das empresas, planos e faturas."""
    return ConsultasDeEmpresas(conexao or db.obter())


def empresa(conexao, empresa_id):
    """A ficha completa (para as telas)."""
    return consultas(conexao).ficha(empresa_id)


def uso(conexao, empresa_id):
    return RepositorioDeLimitesSQLite(conexao).uso(empresa_id)


def pode_cadastrar_tela(conexao, empresa_id):
    repo = RepositorioDeLimitesSQLite(conexao)
    return repo.limites(empresa_id).cabe_mais_uma_tela(repo.uso(empresa_id))


def cabe_no_armazenamento(conexao, empresa_id, bytes_novos):
    repo = RepositorioDeLimitesSQLite(conexao)
    return repo.limites(empresa_id).cabe_no_armazenamento(repo.uso(empresa_id), bytes_novos)
