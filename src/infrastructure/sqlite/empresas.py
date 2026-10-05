"""Empresas no SQLite deste painel: limites, uso e a administração pela plataforma.

A tabela empresas daqui não tem código da loja, módulos nem dados de cadastro.
"""

import sqlite3
from collections.abc import Mapping

from src.domain.empresas import DadosDaEmpresa, EmpresaCliente, Limites, Uso


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


class RepositorioDaPlataformaSQLite(RepositorioDeLimitesSQLite):
    """A plataforma administrando as empresas clientes. Aqui não há código da loja, módulos nem dados de cadastro."""

    def cliente(self, empresa_id: int) -> EmpresaCliente | None:
        linha = self._c.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,)).fetchone()
        if linha is None:
            return None
        return EmpresaCliente(id=linha["id"], nome=linha["nome"], ativa=bool(linha["ativa"]),
                              motivo_suspensao=linha["motivo_suspensao"], modulos_liberados="",
                              tem_assinatura=bool(linha["asaas_assinatura_id"]))

    def codigo_em_uso(self, codigo: str, exceto_id: int | None = None) -> bool:
        return False

    def criar_cliente(self, dados: DadosDaEmpresa, codigo: str, cadastro: Mapping[str, str]) -> int:
        with self._c:
            cursor = self._c.execute("INSERT INTO empresas (nome, limite_telas, limite_mb) VALUES (?, ?, ?)",
                                     (dados.nome, dados.limites.telas, dados.limites.mb))
        return int(cursor.lastrowid or 0)

    def atualizar_cliente(self, empresa_id: int, nome: str, limites: Limites, ativa: bool, motivo_suspensao: str | None,
                          modulos_liberados: str) -> None:
        with self._c:
            self._c.execute(
                "UPDATE empresas SET nome = ?, limite_telas = ?, limite_mb = ?, ativa = ?, motivo_suspensao = ? WHERE id = ?",
                (nome, limites.telas, limites.mb, 1 if ativa else 0, motivo_suspensao, empresa_id))

    def arquivos_de_midia(self, empresa_id: int) -> list[str]:
        return [linha["arquivo"] for linha in self._c.execute("SELECT arquivo FROM propagandas WHERE empresa_id = ?",
                                                                (empresa_id,))]

    def renomear(self, empresa_id: int, nome: str) -> None:
        """O primeiro acesso dá nome à empresa principal."""
        with self._c:
            self._c.execute("UPDATE empresas SET nome = ? WHERE id = ?", (nome[:100], empresa_id))

    def apagar(self, empresa_id: int) -> None:
        with self._c:   # ON DELETE CASCADE apaga usuários, telas, grupos, propagandas, configurações e exibições
            self._c.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
