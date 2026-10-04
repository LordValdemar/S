"""Limites e uso do plano no SQLite deste painel (a tabela empresas daqui não tem código da loja nem módulos)."""

import sqlite3

from src.domain.empresas import Limites, Uso


class RepositorioDeLimitesSQLite:
    def __init__(self, conexao: sqlite3.Connection) -> None:
        self._c = conexao

    def limites(self, empresa_id: int) -> Limites:
        linha = self._c.execute("SELECT limite_telas, limite_mb FROM empresas WHERE id = ?", (empresa_id,)).fetchone()
        return Limites(linha["limite_telas"], linha["limite_mb"]) if linha else Limites(0, 0)

    def uso(self, empresa_id: int) -> Uso:
        telas = self._c.execute("SELECT COUNT(*) FROM telas WHERE empresa_id = ?", (empresa_id,)).fetchone()[0]
        bytes_usados = self._c.execute(
            "SELECT COALESCE(SUM(tamanho), 0) FROM propagandas WHERE empresa_id = ?", (empresa_id,)).fetchone()[0]
        return Uso(int(telas), int(bytes_usados))
