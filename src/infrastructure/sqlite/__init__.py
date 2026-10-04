"""Repositórios no SQLite do Painel local.

propagandas.py, telas.py, exibicoes.py, permissoes.py e datas.py são cópias da plataforma (conferidas por
tests/test_nucleo.py). Este arquivo e empresas.py não são copiados: ajusta o que o banco daqui tem de diferente.
"""

from src.domain.permissoes import Cadastro

from .empresas import RepositorioDaPlataformaSQLite, RepositorioDeLimitesSQLite
from .exibicoes import RepositorioDeExibicoesSQLite
from .permissoes import RepositorioDePermissoesSQLite as _PermissoesDaPlataforma
from .propagandas import RepositorioDePropagandasSQLite
from .telas import RepositorioDeConexoesSQLite, RepositorioDeTelasSQLite


class RepositorioDePermissoesSQLite(_PermissoesDaPlataforma):
    """Aqui usuarios não tem fecha_conta (essa permissão é da Comanda, que esta versão não tem)."""

    def cadastro(self, usuario_id: int) -> Cadastro | None:
        linha = self._c.execute(
            "SELECT id, usuario, papel, plataforma FROM usuarios WHERE id = ? AND empresa_id = ?",
            (usuario_id, self._empresa_id),
        ).fetchone()
        if linha is None:
            return None
        return Cadastro(id=linha["id"], nome=linha["usuario"], papel=linha["papel"], plataforma=bool(linha["plataforma"]))


__all__ = [
    "RepositorioDaPlataformaSQLite", "RepositorioDeConexoesSQLite", "RepositorioDeExibicoesSQLite", "RepositorioDeLimitesSQLite", "RepositorioDePermissoesSQLite", "RepositorioDePropagandasSQLite",
    "RepositorioDeTelasSQLite",
]
