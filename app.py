"""
Painel de Propagandas - sistema simples de sinalização digital.

- Painel de controle (http://localhost:5000/) para enviar imagens e vídeos,
  definir tempo de exibição, ordem, período de validade e o letreiro.
- Tela de exibição (http://localhost:5000/player) para abrir em tela cheia
  na TV ou monitor do estabelecimento.
"""

import json
import os
import threading
import uuid
from datetime import date
from functools import wraps

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_MIDIA = os.environ.get("PASTA_MIDIA", os.path.join(PASTA_BASE, "midia"))
ARQUIVO_DADOS = os.environ.get("ARQUIVO_DADOS", os.path.join(PASTA_BASE, "playlist.json"))
SENHA_ADMIN = os.environ.get("SENHA_ADMIN", "")

EXTENSOES_IMAGEM = {"jpg", "jpeg", "png", "gif", "webp"}
EXTENSOES_VIDEO = {"mp4", "webm", "ogg"}
DURACAO_PADRAO = 10  # segundos

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # até 500 MB por envio

trava = threading.Lock()


# ---------------------------------------------------------------------------
# Armazenamento (arquivo JSON)
# ---------------------------------------------------------------------------

def carregar_dados():
    if not os.path.exists(ARQUIVO_DADOS):
        return {"itens": [], "letreiro": ""}
    with open(ARQUIVO_DADOS, encoding="utf-8") as f:
        dados = json.load(f)
    dados.setdefault("itens", [])
    dados.setdefault("letreiro", "")
    return dados


def salvar_dados(dados):
    # Grava em um arquivo temporário e depois substitui, para não corromper
    # o JSON se o computador desligar no meio da gravação.
    temporario = ARQUIVO_DADOS + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(temporario, ARQUIVO_DADOS)


def buscar_item(dados, item_id):
    for item in dados["itens"]:
        if item["id"] == item_id:
            return item
    abort(404)


def tipo_do_arquivo(nome):
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if extensao in EXTENSOES_IMAGEM:
        return "imagem"
    if extensao in EXTENSOES_VIDEO:
        return "video"
    return None


def esta_no_ar(item, hoje=None):
    """Diz se o item deve aparecer hoje (ativo e dentro do período)."""
    hoje = (hoje or date.today()).isoformat()
    if not item.get("ativo", True):
        return False
    if item.get("inicio") and hoje < item["inicio"]:
        return False
    if item.get("fim") and hoje > item["fim"]:
        return False
    return True


def ler_duracao(valor):
    try:
        return max(1, min(3600, int(valor)))
    except (TypeError, ValueError):
        return DURACAO_PADRAO


# ---------------------------------------------------------------------------
# Senha opcional para o painel (defina a variável SENHA_ADMIN)
# ---------------------------------------------------------------------------

def exige_senha(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if SENHA_ADMIN:
            auth = request.authorization
            if not auth or auth.password != SENHA_ADMIN:
                return Response(
                    "Senha necessária.",
                    401,
                    {"WWW-Authenticate": 'Basic realm="Painel de Propagandas"'},
                )
        return funcao(*args, **kwargs)

    return verificar


# ---------------------------------------------------------------------------
# Painel de controle
# ---------------------------------------------------------------------------

@app.route("/")
@exige_senha
def painel():
    dados = carregar_dados()
    for item in dados["itens"]:
        item["no_ar"] = esta_no_ar(item)
    return render_template("admin.html", dados=dados)


@app.route("/enviar", methods=["POST"])
@exige_senha
def enviar():
    duracao = ler_duracao(request.form.get("duracao"))
    arquivos = request.files.getlist("arquivos")

    with trava:
        dados = carregar_dados()
        os.makedirs(PASTA_MIDIA, exist_ok=True)
        for arquivo in arquivos:
            if not arquivo or not arquivo.filename:
                continue
            tipo = tipo_do_arquivo(arquivo.filename)
            if tipo is None:
                continue
            nome_seguro = secure_filename(arquivo.filename) or "arquivo"
            if "." not in nome_seguro:
                nome_seguro += "." + arquivo.filename.rsplit(".", 1)[-1].lower()
            nome_salvo = f"{uuid.uuid4().hex[:8]}_{nome_seguro}"
            arquivo.save(os.path.join(PASTA_MIDIA, nome_salvo))
            dados["itens"].append({
                "id": uuid.uuid4().hex,
                "nome": arquivo.filename,
                "arquivo": nome_salvo,
                "tipo": tipo,
                "duracao": duracao,
                "ativo": True,
                "inicio": "",
                "fim": "",
            })
        salvar_dados(dados)
    return redirect(url_for("painel"))


@app.route("/item/<item_id>/atualizar", methods=["POST"])
@exige_senha
def atualizar_item(item_id):
    with trava:
        dados = carregar_dados()
        item = buscar_item(dados, item_id)
        item["nome"] = request.form.get("nome", item["nome"]).strip() or item["nome"]
        item["duracao"] = ler_duracao(request.form.get("duracao"))
        item["ativo"] = request.form.get("ativo") == "on"
        item["inicio"] = request.form.get("inicio", "")
        item["fim"] = request.form.get("fim", "")
        salvar_dados(dados)
    return redirect(url_for("painel"))


@app.route("/item/<item_id>/mover/<direcao>", methods=["POST"])
@exige_senha
def mover_item(item_id, direcao):
    with trava:
        dados = carregar_dados()
        itens = dados["itens"]
        posicao = itens.index(buscar_item(dados, item_id))
        destino = posicao - 1 if direcao == "cima" else posicao + 1
        if 0 <= destino < len(itens):
            itens[posicao], itens[destino] = itens[destino], itens[posicao]
            salvar_dados(dados)
    return redirect(url_for("painel"))


@app.route("/item/<item_id>/excluir", methods=["POST"])
@exige_senha
def excluir_item(item_id):
    with trava:
        dados = carregar_dados()
        item = buscar_item(dados, item_id)
        dados["itens"].remove(item)
        salvar_dados(dados)
        caminho = os.path.join(PASTA_MIDIA, item["arquivo"])
        if os.path.exists(caminho):
            os.remove(caminho)
    return redirect(url_for("painel"))


@app.route("/letreiro", methods=["POST"])
@exige_senha
def atualizar_letreiro():
    with trava:
        dados = carregar_dados()
        dados["letreiro"] = request.form.get("letreiro", "").strip()
        salvar_dados(dados)
    return redirect(url_for("painel"))


# ---------------------------------------------------------------------------
# Tela de exibição
# ---------------------------------------------------------------------------

@app.route("/player")
def player():
    return render_template("player.html")


@app.route("/api/playlist")
def api_playlist():
    dados = carregar_dados()
    itens = [
        {
            "id": item["id"],
            "tipo": item["tipo"],
            "url": url_for("midia", arquivo=item["arquivo"]),
            "duracao": item["duracao"],
        }
        for item in dados["itens"]
        if esta_no_ar(item)
    ]
    return jsonify({"itens": itens, "letreiro": dados["letreiro"]})


@app.route("/midia/<path:arquivo>")
def midia(arquivo):
    return send_from_directory(PASTA_MIDIA, arquivo)


if __name__ == "__main__":
    porta = int(os.environ.get("PORTA", 5000))
    print(f"Painel:  http://localhost:{porta}/")
    print(f"Exibição: http://localhost:{porta}/player")
    app.run(host="0.0.0.0", port=porta)
