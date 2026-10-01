"""Páginas públicas de Política de Privacidade e Termos de Uso (modelos para revisão jurídica)."""

from flask import Blueprint, render_template

bp = Blueprint("legal", __name__)


@bp.route("/privacidade")
def privacidade():
    return render_template("privacidade.html")


@bp.route("/termos")
def termos():
    return render_template("termos.html")
