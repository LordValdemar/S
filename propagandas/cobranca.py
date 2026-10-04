"""Planos com preço, assinaturas no Asaas, faturas e bloqueio automático por falta de pagamento.

Fluxo:
1. A plataforma cadastra planos (preço + limites) e escolhe o plano de cada empresa.
2. "Ativar cobrança" cria o cliente e a assinatura mensal no Asaas.
3. O Asaas gera as faturas, avisa o cliente e chama o webhook /webhooks/asaas
   quando uma fatura é criada, paga, vence, etc.
4. Fatura vencida há mais de COBRANCA_TOLERANCIA_DIAS -> empresa suspensa
   (motivo "inadimplencia"); pagou -> reativada sozinha. Suspensão manual
   nunca é desfeita automaticamente.
"""

import hmac
import logging
from datetime import date, timedelta

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from . import agenda, alertas, asaas, db
from .auth import EMPRESA_PRINCIPAL, csrf_isento, login_obrigatorio, plataforma_obrigatoria

bp = Blueprint("cobranca", __name__)
log = logging.getLogger("propagandas.cobranca")

STATUS = {
    "PENDING": ("Aguardando pagamento", "alerta"),
    "AWAITING_RISK_ANALYSIS": ("Em análise", "alerta"),
    "RECEIVED": ("Paga", "no-ar"),
    "CONFIRMED": ("Paga", "no-ar"),
    "RECEIVED_IN_CASH": ("Paga", "no-ar"),
    "OVERDUE": ("Vencida", "fora"),
    "REFUNDED": ("Estornada", "fora"),
    "REFUND_REQUESTED": ("Estorno solicitado", "fora"),
    "CHARGEBACK_REQUESTED": ("Contestada", "fora"),
    "CHARGEBACK_DISPUTE": ("Contestada", "fora"),
    "DELETED": ("Cancelada", ""),
}
PAGAS = {"RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"}
EM_ABERTO = {"PENDING", "OVERDUE", "AWAITING_RISK_ANALYSIS"}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def so_numeros(texto):
    return "".join(c for c in (texto or "") if c.isdigit())


def _digito(numeros, pesos):
    resto = sum(int(n) * p for n, p in zip(numeros, pesos, strict=True)) % 11
    return "0" if resto < 2 else str(11 - resto)


def documento_valido(documento):
    """Confere os dígitos verificadores de CPF (11 dígitos) ou CNPJ (14 dígitos)."""
    d = so_numeros(documento)
    if len(d) == 11 and len(set(d)) > 1:
        return d[9] == _digito(d[:9], range(10, 1, -1)) and d[10] == _digito(d[:10], range(11, 1, -1))
    if len(d) == 14 and len(set(d)) > 1:
        pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        return d[12] == _digito(d[:12], pesos1) and d[13] == _digito(d[:13], [6] + pesos1)
    return False


def reais(centavos):
    """1990 -> 'R$ 19,90'."""
    inteiro, resto = divmod(int(centavos or 0), 100)
    return f"R$ {inteiro:,}".replace(",", ".") + f",{resto:02d}"


def ler_reais(texto):
    """'49,90' ou '49.90' -> 4990 centavos. Retorna None se inválido."""
    texto = (texto or "").strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        valor = round(float(texto) * 100)
    except ValueError:
        return None
    return valor if valor >= 0 else None


def referencia(empresa_id):
    return f"empresa:{empresa_id}"


def faturas_da_empresa(conexao, empresa_id, limite=12):
    return conexao.execute(
        "SELECT * FROM faturas WHERE empresa_id = ? AND status != 'DELETED' ORDER BY vencimento DESC LIMIT ?",
        (empresa_id, limite),
    ).fetchall()


def fatura_vencida(conexao, empresa_id):
    """A fatura vencida mais antiga, se houver."""
    return conexao.execute(
        "SELECT * FROM faturas WHERE empresa_id = ? AND status = 'OVERDUE' ORDER BY vencimento LIMIT 1",
        (empresa_id,),
    ).fetchone()


# ---------------------------------------------------------------------------
# Regras de cobrança
# ---------------------------------------------------------------------------

def gravar_fatura(conexao, empresa_id, pagamento):
    """Cria ou atualiza a fatura local a partir do objeto 'payment' do Asaas."""
    valor = round(float(pagamento.get("value") or 0) * 100)
    pago_em = pagamento.get("clientPaymentDate") or pagamento.get("paymentDate") or pagamento.get("confirmedDate")
    status = "DELETED" if pagamento.get("deleted") else pagamento.get("status", "PENDING")
    link = pagamento.get("invoiceUrl")
    if not (isinstance(link, str) and link.startswith("https://")):
        link = None  # o link vira <a href>: nunca aceitar "javascript:" ou similares
    with conexao:
        conexao.execute(
            """
            INSERT INTO faturas (empresa_id, asaas_id, valor_centavos, vencimento, status, link, pago_em, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asaas_id) DO UPDATE SET
                valor_centavos = excluded.valor_centavos, vencimento = excluded.vencimento,
                status = excluded.status, link = COALESCE(excluded.link, faturas.link),
                pago_em = excluded.pago_em, atualizado_em = excluded.atualizado_em
            """,
            (
                empresa_id, pagamento["id"], valor, pagamento.get("dueDate", ""), status,
                link, pago_em, agenda.para_texto_utc(agenda.agora_utc()),
            ),
        )


def avaliar_inadimplencia(conexao, empresa_id, hoje=None):
    """Suspende ou reativa a empresa conforme as faturas. Retorna 'suspensa', 'reativada' ou None."""
    config = current_app.config
    empresa = conexao.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,)).fetchone()
    if empresa is None or empresa_id == EMPRESA_PRINCIPAL:
        return None
    hoje = hoje or agenda.agora_local().date()
    limite = (hoje - timedelta(days=config["COBRANCA_TOLERANCIA_DIAS"])).isoformat()
    atrasada = conexao.execute(
        "SELECT 1 FROM faturas WHERE empresa_id = ? AND status = 'OVERDUE' AND vencimento < ?",
        (empresa_id, limite),
    ).fetchone()

    if atrasada and empresa["ativa"] and empresa["cobranca_automatica"]:
        with conexao:
            conexao.execute("UPDATE empresas SET ativa = 0, motivo_suspensao = 'inadimplencia' WHERE id = ?", (empresa_id,))
        log.warning("Empresa “%s” suspensa por falta de pagamento", empresa["nome"])
        _avisar_plataforma(f"⛔ “{empresa['nome']}” foi suspensa por falta de pagamento.")
        return "suspensa"
    if not atrasada and not empresa["ativa"] and empresa["motivo_suspensao"] == "inadimplencia":
        with conexao:
            conexao.execute("UPDATE empresas SET ativa = 1, motivo_suspensao = NULL WHERE id = ?", (empresa_id,))
        log.info("Empresa “%s” reativada após pagamento", empresa["nome"])
        _avisar_plataforma(f"💰 “{empresa['nome']}” pagou e foi reativada automaticamente.")
        return "reativada"
    return None


def _avisar_plataforma(mensagem):
    principal = db.obter().execute("SELECT * FROM empresas WHERE id = ?", (EMPRESA_PRINCIPAL,)).fetchone()
    canais = alertas.canais_da_empresa(principal, current_app.config)
    if canais.nomes:
        alertas.enviar_alerta(mensagem, canais)


def sincronizar(conexao, empresa):
    """Busca as faturas da assinatura no Asaas (caso algum webhook tenha se perdido)."""
    if not empresa["asaas_assinatura_id"]:
        return 0
    pagamentos = asaas.faturas_da_assinatura(empresa["asaas_assinatura_id"])
    for pagamento in pagamentos:
        gravar_fatura(conexao, empresa["id"], pagamento)
    # Fatura em aberto aqui que não existe mais no Asaas foi cancelada lá (e o aviso
    # se perdeu): sem isso ela ficaria "vencida" para sempre e suspenderia o cliente.
    ids_no_asaas = {p["id"] for p in pagamentos}
    abertas = conexao.execute(
        f"SELECT asaas_id FROM faturas WHERE empresa_id = ? AND status IN ({','.join('?' * len(EM_ABERTO))})",
        (empresa["id"], *sorted(EM_ABERTO)),
    ).fetchall()
    with conexao:
        for linha in abertas:
            if linha["asaas_id"] not in ids_no_asaas:
                conexao.execute("UPDATE faturas SET status = 'DELETED' WHERE asaas_id = ?", (linha["asaas_id"],))
    avaliar_inadimplencia(conexao, empresa["id"])
    return len(pagamentos)


def sincronizar_todas():
    """Usado pela tarefa diária. Erros numa empresa não impedem as outras."""
    conexao = db.obter()
    for empresa in conexao.execute("SELECT * FROM empresas WHERE asaas_assinatura_id IS NOT NULL").fetchall():
        try:
            sincronizar(conexao, empresa)
        except asaas.ErroAsaas:
            log.exception("Falha ao sincronizar as faturas da empresa %s", empresa["id"])
    for empresa in conexao.execute("SELECT id FROM empresas WHERE cobranca_automatica = 1").fetchall():
        avaliar_inadimplencia(conexao, empresa["id"])  # a tolerância vence com o passar dos dias


# ---------------------------------------------------------------------------
# Webhook do Asaas
# ---------------------------------------------------------------------------

@bp.route("/webhooks/asaas", methods=["POST"])
@csrf_isento
def webhook_asaas():
    esperado = current_app.config["ASAAS_WEBHOOK_TOKEN"]
    recebido = request.headers.get("asaas-access-token", "")
    if not esperado or not hmac.compare_digest(recebido, esperado):
        log.warning("Webhook do Asaas com token inválido (IP %s)", request.remote_addr)
        abort(401)

    evento = request.get_json(silent=True)
    if not isinstance(evento, dict):
        abort(400)
    pagamento = evento.get("payment")
    conexao = db.obter()

    evento_id = str(evento.get("id") or "")[:100]
    # O Asaas pode reenviar o mesmo evento. O evento só é marcado como processado
    # no fim: se algo falhar no meio, o reenvio é aplicado (gravar a fatura é idempotente).
    if evento_id and conexao.execute("SELECT 1 FROM webhook_eventos WHERE id = ?", (evento_id,)).fetchone():
        return {"ok": True, "repetido": True}

    resposta = {"ok": True, "ignorado": True}
    empresa = None
    if isinstance(pagamento, dict) and isinstance(pagamento.get("id"), str) and pagamento.get("subscription"):
        empresa = conexao.execute(
            "SELECT * FROM empresas WHERE asaas_assinatura_id = ?", (pagamento["subscription"],)
        ).fetchone()
        if empresa is None:
            log.info("Webhook do Asaas para assinatura desconhecida %s", pagamento["subscription"])

    if empresa is not None:
        # O conteúdo do webhook NUNCA é usado como verdade: ele só avisa que algo mudou.
        # A situação da fatura é consultada direto na API do Asaas. Assim, mesmo quem
        # descobrir o token não consegue liberar um cliente com um aviso falso de pagamento.
        try:
            verdadeiro = asaas.buscar_fatura(pagamento["id"])
        except asaas.ErroAsaas as erro:
            # A sincronização de hora em hora aplica depois. Responde 200 para o Asaas
            # não pausar a fila, mas NÃO marca o evento como processado.
            log.warning("Webhook: não foi possível confirmar a fatura %s no Asaas (%s)", pagamento["id"], erro)
            return {"ok": True, "pendente": True}
        if verdadeiro.get("id") != pagamento["id"] or verdadeiro.get("subscription") != empresa["asaas_assinatura_id"]:
            log.warning("Webhook: a fatura %s não pertence à assinatura da empresa %s", pagamento["id"], empresa["id"])
            return {"ok": True, "ignorado": True}
        gravar_fatura(conexao, empresa["id"], verdadeiro)
        resultado = avaliar_inadimplencia(conexao, empresa["id"])
        log.info("Asaas: %s da fatura %s (empresa %s), situação confirmada: %s",
                 evento.get("event"), pagamento["id"], empresa["id"], verdadeiro.get("status"))
        resposta = {"ok": True, "empresa": empresa["id"], "resultado": resultado}

    if evento_id:
        with conexao:
            conexao.execute(
                "INSERT OR IGNORE INTO webhook_eventos (id, recebido_em) VALUES (?, ?)",
                (evento_id, agenda.para_texto_utc(agenda.agora_utc())),
            )
    # Sempre 200 para eventos válidos (mesmo os ignorados): erros repetidos fazem o Asaas pausar a fila.
    return resposta


# ---------------------------------------------------------------------------
# Cliente: página de pagamento (acessível mesmo com a empresa suspensa)
# ---------------------------------------------------------------------------

@bp.route("/pagamento")
@login_obrigatorio()
def pagamento():
    conexao = db.obter()
    empresa = conexao.execute("SELECT * FROM empresas WHERE id = ?", (g.empresa_id,)).fetchone()
    return render_template(
        "pagamento.html",
        empresa=empresa,
        faturas=faturas_da_empresa(conexao, g.empresa_id),
        STATUS=STATUS,
        EM_ABERTO=EM_ABERTO,
    )


# ---------------------------------------------------------------------------
# Plataforma: planos e assinaturas
# ---------------------------------------------------------------------------

def _plano_do_formulario():
    nome = request.form.get("nome", "").strip()[:60]
    preco = ler_reais(request.form.get("preco"))
    limites = []
    for campo in ("limite_telas", "limite_mb"):
        valor = request.form.get(campo, "").strip()
        limites.append(int(valor) if valor.isdigit() else None)
    return nome, preco, *limites


@bp.route("/plataforma/planos/novo", methods=["POST"])
@plataforma_obrigatoria
def novo_plano():
    nome, preco, limite_telas, limite_mb = _plano_do_formulario()
    conexao = db.obter()
    if not nome or preco is None:
        flash("Informe o nome e o preço do plano (ex.: 49,90).", "erro")
    elif conexao.execute("SELECT 1 FROM planos WHERE nome = ?", (nome,)).fetchone():
        flash(f"O plano “{nome}” já existe.", "erro")
    else:
        with conexao:
            conexao.execute(
                "INSERT INTO planos (nome, preco_centavos, limite_telas, limite_mb) VALUES (?, ?, ?, ?)",
                (nome, preco, limite_telas, limite_mb),
            )
        log.info("“%s” criou o plano “%s” (%s)", g.usuario["usuario"], nome, reais(preco))
        flash(f"Plano “{nome}” criado.", "ok")
    return redirect(url_for("plataforma.lista"))


@bp.route("/plataforma/planos/<int:plano_id>/atualizar", methods=["POST"])
@plataforma_obrigatoria
def atualizar_plano(plano_id):
    conexao = db.obter()
    if conexao.execute("SELECT 1 FROM planos WHERE id = ?", (plano_id,)).fetchone() is None:
        abort(404)
    nome, preco, limite_telas, limite_mb = _plano_do_formulario()
    if not nome or preco is None:
        flash("Informe o nome e o preço do plano.", "erro")
        return redirect(url_for("plataforma.lista"))
    with conexao:
        conexao.execute(
            "UPDATE planos SET nome = ?, preco_centavos = ?, limite_telas = ?, limite_mb = ?, ativo = ? WHERE id = ?",
            (nome, preco, limite_telas, limite_mb, 1 if request.form.get("ativo") == "on" else 0, plano_id),
        )
        # Os limites valem na hora para todas as empresas do plano.
        conexao.execute(
            "UPDATE empresas SET limite_telas = ?, limite_mb = ? WHERE plano_id = ?", (limite_telas, limite_mb, plano_id)
        )
    flash("Plano atualizado. Assinaturas já ativas mantêm o preço até você mudar o plano delas.", "ok")
    return redirect(url_for("plataforma.lista"))


def _buscar_empresa(conexao, empresa_id):
    empresa = conexao.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,)).fetchone()
    if empresa is None:
        abort(404)
    return empresa


@bp.route("/plataforma/empresas/<int:empresa_id>/cobranca", methods=["POST"])
@plataforma_obrigatoria
def salvar_cobranca(empresa_id):
    """Plano, CPF/CNPJ e e-mail de cobrança. Se a assinatura já existe, atualiza o valor no Asaas."""
    conexao = db.obter()
    empresa = _buscar_empresa(conexao, empresa_id)
    plano_id = request.form.get("plano_id", "")
    plano = None
    if plano_id.isdigit():
        plano = conexao.execute("SELECT * FROM planos WHERE id = ?", (int(plano_id),)).fetchone()
    documento = so_numeros(request.form.get("documento"))
    email = request.form.get("email_cobranca", "").strip()[:200]

    if documento and not documento_valido(documento):
        flash("CPF ou CNPJ inválido.", "erro")
        return redirect(url_for("plataforma.lista"))
    if email and "@" not in email:
        flash("E-mail de cobrança inválido.", "erro")
        return redirect(url_for("plataforma.lista"))

    if empresa["asaas_assinatura_id"] and plano is None:
        flash("Cancele a cobrança antes de tirar o plano desta empresa.", "erro")
        return redirect(url_for("plataforma.lista"))
    if empresa["asaas_assinatura_id"] and plano["id"] != empresa["plano_id"]:
        try:
            asaas.atualizar_assinatura(empresa["asaas_assinatura_id"], plano["preco_centavos"], f"Plano {plano['nome']}")
        except asaas.ErroAsaas as erro:
            flash(f"O Asaas recusou a mudança de plano: {erro}", "erro")
            return redirect(url_for("plataforma.lista"))

    with conexao:
        conexao.execute(
            "UPDATE empresas SET plano_id = ?, documento = ?, email_cobranca = ?, cobranca_automatica = ? WHERE id = ?",
            (plano["id"] if plano else None, documento, email,
             1 if request.form.get("cobranca_automatica") == "on" else 0, empresa_id),
        )
        if plano:
            conexao.execute(
                "UPDATE empresas SET limite_telas = ?, limite_mb = ? WHERE id = ?",
                (plano["limite_telas"], plano["limite_mb"], empresa_id),
            )
    log.info("“%s” alterou a cobrança da empresa “%s”", g.usuario["usuario"], empresa["nome"])
    flash("Dados de cobrança salvos.", "ok")
    return redirect(url_for("plataforma.lista"))


@bp.route("/plataforma/empresas/<int:empresa_id>/cobranca/ativar", methods=["POST"])
@plataforma_obrigatoria
def ativar_cobranca(empresa_id):
    conexao = db.obter()
    empresa = _buscar_empresa(conexao, empresa_id)
    plano = conexao.execute("SELECT * FROM planos WHERE id = ?", (empresa["plano_id"],)).fetchone()
    try:
        vencimento = date.fromisoformat(request.form.get("primeiro_vencimento", ""))
    except ValueError:
        vencimento = None

    erro = None
    if empresa["asaas_assinatura_id"]:
        erro = "a cobrança já está ativa"
    elif plano is None or plano["preco_centavos"] <= 0:
        erro = "escolha um plano com preço"
    elif not documento_valido(empresa["documento"]):
        erro = "informe um CPF ou CNPJ válido"
    elif vencimento is None or vencimento < agenda.agora_local().date():
        erro = "informe a data do primeiro vencimento (hoje ou depois)"
    if erro:
        flash(f"Não foi possível ativar a cobrança: {erro}.", "erro")
        return redirect(url_for("plataforma.lista"))

    try:
        cliente_id = empresa["asaas_cliente_id"]
        if not cliente_id:
            cliente_id = asaas.criar_cliente(
                empresa["nome"], empresa["documento"], empresa["email_cobranca"], referencia(empresa_id)
            )["id"]
            with conexao:
                conexao.execute("UPDATE empresas SET asaas_cliente_id = ? WHERE id = ?", (cliente_id, empresa_id))
        assinatura = asaas.criar_assinatura(
            cliente_id, plano["preco_centavos"], vencimento.isoformat(), f"Plano {plano['nome']}", referencia(empresa_id)
        )
    except asaas.ErroAsaas as erro_asaas:
        flash(f"O Asaas recusou: {erro_asaas}", "erro")
        return redirect(url_for("plataforma.lista"))

    with conexao:
        conexao.execute(
            "UPDATE empresas SET asaas_assinatura_id = ?, cobranca_automatica = 1 WHERE id = ?",
            (assinatura["id"], empresa_id),
        )
    try:
        sincronizar(conexao, _buscar_empresa(conexao, empresa_id))  # traz a primeira fatura
    except asaas.ErroAsaas:
        log.exception("Assinatura criada, mas a primeira sincronização falhou")
    log.info("“%s” ativou a cobrança de “%s” (%s/mês)", g.usuario["usuario"], empresa["nome"], reais(plano["preco_centavos"]))
    flash(f"Cobrança ativada: {reais(plano['preco_centavos'])}/mês. O Asaas envia as faturas ao cliente.", "ok")
    return redirect(url_for("plataforma.lista"))


@bp.route("/plataforma/empresas/<int:empresa_id>/cobranca/cancelar", methods=["POST"])
@plataforma_obrigatoria
def cancelar_cobranca(empresa_id):
    conexao = db.obter()
    empresa = _buscar_empresa(conexao, empresa_id)
    if empresa["asaas_assinatura_id"]:
        try:
            asaas.cancelar_assinatura(empresa["asaas_assinatura_id"])
        except asaas.ErroAsaas as erro:
            flash(f"O Asaas recusou o cancelamento: {erro}", "erro")
            return redirect(url_for("plataforma.lista"))
    with conexao:
        conexao.execute(
            "UPDATE empresas SET asaas_assinatura_id = NULL, cobranca_automatica = 0 WHERE id = ?", (empresa_id,)
        )
    avaliar_inadimplencia(conexao, empresa_id)
    log.info("“%s” cancelou a cobrança de “%s”", g.usuario["usuario"], empresa["nome"])
    flash("Cobrança cancelada. Nenhuma nova fatura será gerada.", "ok")
    return redirect(url_for("plataforma.lista"))


@bp.route("/plataforma/empresas/<int:empresa_id>/cobranca/sincronizar", methods=["POST"])
@plataforma_obrigatoria
def sincronizar_empresa(empresa_id):
    conexao = db.obter()
    try:
        total = sincronizar(conexao, _buscar_empresa(conexao, empresa_id))
    except asaas.ErroAsaas as erro:
        flash(f"Falha ao consultar o Asaas: {erro}", "erro")
    else:
        flash(f"{total} fatura(s) atualizada(s).", "ok")
    return redirect(url_for("plataforma.lista"))
