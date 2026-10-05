"""Repositórios no SQLite do Painel local.

propagandas.py, telas.py, exibicoes.py, monitoramento.py, consultas_painel.py, cobranca.py, permissoes.py e datas.py
são cópias da plataforma (conferidas por tests/test_nucleo.py). Este arquivo, contas.py, consultas_empresas.py e
empresas.py são só deste painel: o banco daqui não tem o código da loja, os módulos, a Comanda nem o ponto.
"""

from src.domain.permissoes import Cadastro

from .cobranca import RepositorioDeCobrancaSQLite
from .consultas_empresas import ConsultasDeEmpresas
from .consultas_painel import ConsultasDoPainel
from .contas import RepositorioDeContasSQLite
from .empresas import RepositorioDaEmpresaSQLite, RepositorioDaPlataformaSQLite, RepositorioDeLimitesSQLite
from .exibicoes import RepositorioDeExibicoesSQLite, apagar_exibicoes_anteriores
from .monitoramento import RepositorioDeMonitoramentoSQLite
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
    "ConsultasDeEmpresas", "ConsultasDoPainel", "RepositorioDeCobrancaSQLite", "RepositorioDeContasSQLite",
    "RepositorioDaEmpresaSQLite", "RepositorioDaPlataformaSQLite", "RepositorioDeConexoesSQLite", "RepositorioDeExibicoesSQLite",
    "RepositorioDeLimitesSQLite", "RepositorioDeMonitoramentoSQLite", "RepositorioDePermissoesSQLite",
    "RepositorioDePropagandasSQLite", "RepositorioDeTelasSQLite", "apagar_exibicoes_anteriores",
]
