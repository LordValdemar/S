"""Relatório de exibições (proof of play), com exportação CSV. As regras ficam no núcleo (src/domain/relatorios)."""

import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, g, render_template, request

from src.domain.periodo import Periodo
from src.domain.relatorios import RelatorioDeExibicoes
from src.domain.relatorios.exibicoes import DIAS_PADRAO
from src.infrastructure.sqlite import RepositorioDeExibicoesSQLite

from . import agenda, db, permissoes

bp = Blueprint("relatorios", __name__)


def _ler_filtros():
    hoje = agenda.agora_local().date()
    periodo = Periodo.ler(request.args.get("de"), request.args.get("ate"), hoje - timedelta(days=DIAS_PADRAO - 1), hoje)
    tela = request.args.get("tela", "")
    return periodo.inicio, periodo.fim, int(tela) if tela.isdigit() else None


def _intervalo_utc(de, ate):
    return agenda.inicio_do_dia_utc(de), agenda.inicio_do_dia_utc(ate + timedelta(days=1))


def relatorio():
    return RelatorioDeExibicoes(RepositorioDeExibicoesSQLite(db.obter(), g.empresa_id))


@bp.route("/relatorios")
@permissoes.exigir("relatorios")
def resumo():
    de, ate, tela_id = _ler_filtros()
    dados = relatorio().resumo(*_intervalo_utc(de, ate), tela_id)
    telas = db.obter().execute("SELECT id, nome FROM telas WHERE empresa_id = ? ORDER BY nome", (g.empresa_id,)).fetchall()
    return render_template("relatorios.html", de=de, ate=ate, tela_id=tela_id, telas=telas,
                           por_propaganda=dados.por_propaganda, por_tela=dados.por_tela,
                           total_exibicoes=dados.total_exibicoes, total_tempo=dados.total_tempo)


@bp.route("/relatorios.csv")
@permissoes.exigir("relatorios")
def exportar():
    """Uma linha por dia, tela e propaganda. O dia é o local: usa o fuso do primeiro dia do período,
    o que é exato em regiões sem horário de verão (como o Brasil hoje)."""
    de, ate, tela_id = _ler_filtros()
    saida = io.StringIO()
    # Ponto e vírgula e BOM: abre direto no Excel em português, com os acentos.
    csv.writer(saida, delimiter=";").writerows(relatorio().planilha(*_intervalo_utc(de, ate), tela_id, agenda.offset_minutos(de)))
    return Response("﻿" + saida.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="exibicoes_{de:%Y%m%d}_{ate:%Y%m%d}.csv"'})
