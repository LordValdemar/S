"""Limites do plano de cada empresa (número de telas e armazenamento)."""

MB = 1024 * 1024


def empresa(conexao, empresa_id):
    return conexao.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,)).fetchone()


def uso(conexao, empresa_id):
    telas = conexao.execute("SELECT COUNT(*) FROM telas WHERE empresa_id = ?", (empresa_id,)).fetchone()[0]
    bytes_usados = conexao.execute(
        "SELECT COALESCE(SUM(tamanho), 0) FROM propagandas WHERE empresa_id = ?", (empresa_id,)
    ).fetchone()[0]
    return {"telas": telas, "bytes": bytes_usados, "mb": bytes_usados / MB}


def pode_cadastrar_tela(conexao, empresa_id):
    limite = empresa(conexao, empresa_id)["limite_telas"]
    return limite is None or uso(conexao, empresa_id)["telas"] < limite


def cabe_no_armazenamento(conexao, empresa_id, bytes_novos):
    limite = empresa(conexao, empresa_id)["limite_mb"]
    return limite is None or uso(conexao, empresa_id)["bytes"] + bytes_novos <= limite * MB
