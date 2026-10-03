"""Ajustes da Comanda de cada loja: nome e endereço no cupom e taxa de serviço."""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import modulos
from .base import gravar_config, ler_config, papel_exigido
from .comandas import taxa_padrao

bp = Blueprint("comanda_ajustes", __name__, url_prefix="/comanda/ajustes")
bp.before_request(modulos.exigir("comanda"))


@bp.route("/", methods=["GET", "POST"])
@papel_exigido()
def pagina():
    if request.method == "POST":
        try:
            taxa = float(request.form.get("taxa_servico", "10").replace(",", ".") or 0)
        except ValueError:
            taxa = -1
        if not 0 <= taxa <= 30:
            flash("A taxa de serviço vai de 0 a 30%.", "erro")
            return redirect(url_for("comanda_ajustes.pagina"))
        gravar_config("nome_estabelecimento", request.form.get("nome_estabelecimento", "").strip()[:80])
        gravar_config("endereco", request.form.get("endereco", "").strip()[:160])
        gravar_config("rodape_cupom", request.form.get("rodape_cupom", "").strip()[:160])
        gravar_config("taxa_servico", f"{taxa:g}")
        flash("Ajustes salvos. A nova taxa vale para as comandas abertas daqui em diante.", "ok")
        return redirect(url_for("comanda_ajustes.pagina"))
    return render_template(
        "comanda/ajustes.html",
        nome_estabelecimento=ler_config("nome_estabelecimento") or g.usuario["empresa_nome"],
        endereco=ler_config("endereco"),
        rodape_cupom=ler_config("rodape_cupom", "Obrigado pela preferência!"),
        taxa_servico=f"{taxa_padrao():g}".replace(".", ","),
    )
