"""Limites do plano de cada empresa (número de telas e armazenamento). As regras ficam no núcleo (src/domain/empresas)."""

from src.domain.empresas import MB
from src.infrastructure.sqlite import RepositorioDeLimitesSQLite

__all__ = ["MB", "cabe_no_armazenamento", "empresa", "pode_cadastrar_tela", "uso"]


def empresa(conexao, empresa_id):
    """A ficha completa (para as telas)."""
    return conexao.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,)).fetchone()


def uso(conexao, empresa_id):
    return RepositorioDeLimitesSQLite(conexao).uso(empresa_id)


def pode_cadastrar_tela(conexao, empresa_id):
    repo = RepositorioDeLimitesSQLite(conexao)
    return repo.limites(empresa_id).cabe_mais_uma_tela(repo.uso(empresa_id))


def cabe_no_armazenamento(conexao, empresa_id, bytes_novos):
    repo = RepositorioDeLimitesSQLite(conexao)
    return repo.limites(empresa_id).cabe_no_armazenamento(repo.uso(empresa_id), bytes_novos)
