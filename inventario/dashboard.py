"""Cálculos do Dashboard Gerencial.

Tudo sai do banco, nada é estimado. Quando um número não pode ser
calculado, ele volta como "indisponível" com o motivo, e as falhas de
cadastro que afetam a conta voltam em `avisos`, para o painel mostrar.

Regras que valem para o painel inteiro
--------------------------------------
* **Período**: de 1 a 12 meses inteiros (do dia 1 do mês inicial ao último
  dia do mês final). O que é "foto" (receita recorrente, contratos ativos,
  chamados em aberto) é tirado no fim do período — ou **hoje**, se o período
  ainda não acabou — e comparado com a véspera do início. O resto (novas
  contratações, perdas, instalações, retiradas, chamados encerrados) soma
  tudo o que aconteceu dentro do período.
* **Receita recorrente** = soma do **valor mensal dos contratos ativos** na
  data de referência. O valor mensal de um contrato numa data é o do último
  aditivo até ela (cada aditivo guarda o novo total) ou, sem aditivo, o
  "Valor mensal" do contrato (ver `Contrato.valor_mensal_em`). Não é a soma
  das máquinas: muitas não são cobradas à parte (franquia de impressão,
  monitor ou estabilizador dentro de um contrato maior).
* **Nova contratação** = contrato novo (pelo valor mensal dele) ou aditivo
  que aumentou o valor mensal (pela diferença), mesmo num contrato antigo.
* **Receita perdida** = valor mensal dos contratos cancelados no período mais as
  reduções por aditivo (aditivo com valor menor que o anterior).
* **Instalação** = início de uma locação (`Locacao.data_inicio`).
  **Retirada** = fim de uma locação encerrada (`Locacao.data_fim`). São as
  datas reais da operação, não a situação atual da máquina: a mesma
  máquina pode ir e voltar várias vezes e cada ida/volta conta uma vez.
* **Chamado dentro do SLA** = encerrado em até `Chamado.HORAS_ATE_ATRASO`
  horas (24h), o mesmo prazo que dispara a sirene do painel técnico.
"""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from .models import Chamado, Contrato, Locacao, Manutencao, formata_duracao

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
    "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
MESES_CURTOS = [m[:3] for m in MESES]
MESES_NO_GRAFICO = 12
MAXIMO_DE_MESES = 12
ZERO = Decimal("0")


# ----- Datas -----

def primeiro_dia(ano, mes):
    return date(ano, mes, 1)


def ultimo_dia(ano, mes):
    return date(ano, mes, monthrange(ano, mes)[1])


def entre(dia, inicio, fim):
    return dia is not None and inicio <= dia <= fim


def proximo_mes(ano, mes):
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def meses_entre(de, ate):
    """Lista (ano, mes) de `de` até `ate`, inclusive."""
    meses = [de]
    while meses[-1] < ate:
        meses.append(proximo_mes(*meses[-1]))
    return meses


def periodo_valido(de, ate, hoje):
    """Arruma o período pedido: na ordem certa, nada no futuro, até 12 meses.

    Devolve (de, ate, aviso); `aviso` explica o que foi ajustado.
    """
    atual = (hoje.year, hoje.month)
    aviso = ""
    if de > ate:
        de, ate = ate, de
    if ate > atual:
        ate, aviso = atual, "O período não pode passar do mês atual."
        de = min(de, ate)
    meses = meses_entre(de, ate)
    if len(meses) > MAXIMO_DE_MESES:
        de = meses[-MAXIMO_DE_MESES]
        aviso = (
            f"O período vai até {MAXIMO_DE_MESES} meses: ficou de "
            f"{rotulo_mes(*de)} a {rotulo_mes(*ate)}."
        )
    return de, ate, aviso


def mes_anterior(ano, mes):
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def ultimos_meses(ano, mes, quantos=MESES_NO_GRAFICO):
    """Lista (ano, mes) do mais antigo ao mês pedido, inclusive."""
    meses = [(ano, mes)]
    for _ in range(quantos - 1):
        meses.append(mes_anterior(*meses[-1]))
    return list(reversed(meses))


def _inicio_do_dia(dia):
    return timezone.make_aware(datetime.combine(dia, time.min))


def _intervalo_horas(inicio, fim, hoje=None):
    """[início do 1º dia, fim do último dia ou agora) em horário de Maceió."""
    comeco = _inicio_do_dia(inicio)
    final = _inicio_do_dia(fim + timedelta(days=1))
    agora = timezone.now() if hoje is None else _inicio_do_dia(hoje + timedelta(days=1))
    return comeco, min(final, agora)


def rotulo_mes(ano, mes):
    return f"{MESES[mes - 1]} de {ano}"


def rotulo_periodo(de, ate):
    """Ex.: "Março de 2026", "Junho a Novembro de 2026", "Dezembro de 2025 a Maio de 2026"."""
    if de == ate:
        return rotulo_mes(*de)
    if de[0] == ate[0]:
        return f"{MESES[de[1] - 1]} a {MESES[ate[1] - 1]} de {ate[0]}"
    return f"{rotulo_mes(*de)} a {rotulo_mes(*ate)}"


def variacao_percentual(atual, anterior):
    """None quando não há base de comparação (mês anterior zerado)."""
    if not anterior:
        return None
    return float((Decimal(atual) - Decimal(anterior)) / Decimal(anterior) * 100)


def _nome_cliente(contrato):
    return str(contrato.cliente) if contrato.cliente else "Sem cliente"


# ----- Contratos e receita -----

def _contratos(cliente=None):
    qs = Contrato.objects.select_related("cliente", "cancelado_por").prefetch_related("aditivos")
    if cliente:
        qs = qs.filter(cliente=cliente)
    contratos = list(qs)
    for c in contratos:
        # Do mais antigo ao mais novo; os sem valor (antigos) não contam.
        c.aditivos_com_valor = sorted(
            (a for a in c.aditivos.all() if a.valor is not None),
            key=lambda a: (a.data, a.numero),
        )
    return contratos


def valor_em(contrato, dia):
    return contrato.valor_mensal_em(dia, contrato.aditivos_com_valor)


def ativo_em(contrato, dia):
    return contrato.data_contrato <= dia and (
        contrato.data_cancelamento is None or contrato.data_cancelamento > dia
    )


def receita_recorrente(contratos, dia):
    ativos = [c for c in contratos if ativo_em(c, dia)]
    por_cliente = defaultdict(lambda: {"valor": ZERO, "contratos": 0, "sem_valor": 0})
    total = ZERO
    sem_valor = []
    for c in ativos:
        valor = valor_em(c, dia)
        linha = por_cliente[_nome_cliente(c)]
        linha["contratos"] += 1
        if valor is None:
            linha["sem_valor"] += 1
            sem_valor.append(c)
        else:
            linha["valor"] += valor
            total += valor
    return {
        "valor": total,
        "contratos": len(ativos),
        "sem_valor": sem_valor,
        "por_cliente": sorted(
            ({"cliente": nome, **linha} for nome, linha in por_cliente.items()),
            key=lambda linha: (-linha["valor"], linha["cliente"]),
        ),
    }


def _mudancas_por_aditivo(contrato):
    """Cada aditivo com a diferença que causou no valor mensal.

    O valor de antes é o do aditivo anterior (ou o do contrato, para o
    primeiro). Sem valor de antes, a diferença fica desconhecida (None).
    """
    anterior = contrato.valor
    for aditivo in contrato.aditivos_com_valor:
        diferenca = None if anterior is None else aditivo.valor - anterior
        yield aditivo, anterior, diferenca
        anterior = aditivo.valor


def contratacoes_e_perdas(contratos, locacoes, inicio, fim):
    """Novas contratações (contrato novo ou aditivo que aumentou o valor) e
    perdas (cancelamento ou aditivo que reduziu o valor) do período."""
    maquinas = defaultdict(int)
    for loc in locacoes:
        if loc.contrato_id and loc.ativa:
            maquinas[loc.contrato_id] += 1

    novas, perdas, sem_base = [], [], []
    for c in contratos:
        cliente = _nome_cliente(c)
        if entre(c.data_contrato, inicio, fim):
            novas.append({
                "tipo": "contrato", "contrato": c, "cliente": cliente,
                "data": c.data_contrato, "descricao": c.titulo or "Contrato novo",
                "valor": c.valor, "anterior": None, "maquinas": maquinas[c.pk],
            })
        for aditivo, anterior, diferenca in _mudancas_por_aditivo(c):
            if not entre(aditivo.data, inicio, fim):
                continue
            if c.data_cancelamento and aditivo.data >= c.data_cancelamento:
                continue
            if diferenca is None:
                sem_base.append(aditivo)
                continue
            linha = {
                "tipo": "aditivo", "contrato": c, "cliente": cliente,
                "data": aditivo.data, "aditivo": aditivo,
                "descricao": f"Aditivo {aditivo.numero}" + (f" — {aditivo.descricao}" if aditivo.descricao else ""),
                "anterior": anterior, "novo": aditivo.valor,
                "valor": abs(diferenca), "maquinas": maquinas[c.pk],
            }
            if diferenca > 0:
                novas.append(linha)
            elif diferenca < 0:
                perdas.append({**linha, "motivo": aditivo.observacoes})
        if entre(c.data_cancelamento, inicio, fim):
            # O que deixa de entrar: o valor mensal que valia na véspera.
            valor = valor_em(c, c.data_cancelamento - timedelta(days=1))
            perdas.append({
                "tipo": "cancelamento", "contrato": c, "cliente": cliente,
                "data": c.data_cancelamento, "descricao": "Contrato cancelado",
                "motivo": c.motivo_cancelamento, "valor": valor,
                "anterior": valor, "novo": ZERO,
            })

    novas.sort(key=lambda linha: (linha["data"], linha["cliente"]))
    # Maiores perdas primeiro
    perdas.sort(key=lambda linha: (-(linha["valor"] or ZERO), linha["data"]))

    por_cliente = defaultdict(lambda: ZERO)
    for linha in perdas:
        por_cliente[linha["cliente"]] += linha["valor"] or ZERO

    cancelamentos = [linha for linha in perdas if linha["tipo"] == "cancelamento"]
    novos_contratos = [linha for linha in novas if linha["tipo"] == "contrato"]
    return {
        "novas": {
            "linhas": novas,
            "quantidade": len(novas),
            "contratos": len(novos_contratos),
            "aditivos": len(novas) - len(novos_contratos),
            "valor": sum((linha["valor"] or ZERO for linha in novas), ZERO),
            "sem_valor": sum(1 for linha in novos_contratos if linha["valor"] is None),
        },
        "perdas": {
            "linhas": perdas,
            "valor": sum((linha["valor"] or ZERO for linha in perdas), ZERO),
            "cancelamentos": len(cancelamentos),
            "reducoes": len(perdas) - len(cancelamentos),
            "por_cliente": sorted(por_cliente.items(), key=lambda item: (-item[1], item[0])),
            "sem_valor": sum(1 for linha in cancelamentos if linha["valor"] is None),
        },
        "aditivos_sem_base": sem_base,
    }


# ----- Locações (movimentação de máquinas) -----

def _locacoes(cliente=None):
    qs = Locacao.objects.select_related(
        "equipamento", "equipamento__produto", "cliente", "contrato"
    )
    if cliente:
        qs = qs.filter(cliente=cliente)
    return qs


def vigente_em(locacao, dia):
    """A máquina estava com o cliente nesse dia?"""
    if locacao.data_inicio > dia:
        return False
    if locacao.ativa:
        return True
    # Encerrada sem data de fim: não dá para saber até quando valeu.
    return locacao.data_fim is not None and locacao.data_fim > dia


def _linha_maquina(loc, data):
    eq = loc.equipamento
    return {
        "data": data,
        "equipamento": str(eq),
        "equipamento_id": eq.pk,
        "inf": f"INF-{eq.numero_patrimonio}" if eq.numero_patrimonio else "—",
        "marca_modelo": f"{eq.marca} {eq.modelo}".strip() or "—",
        "cliente": str(loc.cliente),
        "valor": loc.valor,
        "sem_contrato": not loc.contrato_id,
    }


def _ranking(linhas):
    contagem = defaultdict(int)
    for linha in linhas:
        contagem[linha["cliente"]] += 1
    return sorted(contagem.items(), key=lambda item: (-item[1], item[0]))


def movimentacao_equipamentos(locacoes, inicio, fim):
    instalados = [
        _linha_maquina(loc, loc.data_inicio)
        for loc in locacoes if entre(loc.data_inicio, inicio, fim)
    ]

    retirados = []
    for loc in locacoes:
        if loc.ativa or not entre(loc.data_fim, inicio, fim):
            continue
        linha = _linha_maquina(loc, loc.data_fim)
        contrato = loc.contrato
        # O motivo só existe quando a retirada veio de um cancelamento
        if contrato and contrato.data_cancelamento == loc.data_fim:
            linha["motivo"] = f"Cancelamento do contrato: {contrato.motivo_cancelamento}"
        else:
            linha["motivo"] = ""
        retirados.append(linha)

    instalados.sort(key=lambda linha: (linha["data"], linha["cliente"]))
    retirados.sort(key=lambda linha: (linha["data"], linha["cliente"]))
    return {
        "instalados": instalados,
        "retirados": retirados,
        "ranking_instalados": _ranking(instalados),
        "ranking_retirados": _ranking(retirados),
        # A importação por PDF cria locação com R$ 0,00, sem contrato, no dia
        # da importação — essas "instalações" podem não ser reais.
        "instalados_suspeitos": sum(
            1 for linha in instalados if not linha["valor"] and linha["sem_contrato"]
        ),
    }


# ----- Chamados (SLA) -----

def _chamados(cliente=None):
    qs = Chamado.objects.select_related("cliente", "equipamento", "tecnico")
    if cliente:
        qs = qs.filter(cliente=cliente)
    return qs


def _linha_chamado(ch, tempo):
    return {
        "chamado": ch,
        "numero": ch.numero_os,
        "cliente": str(ch.cliente) if ch.cliente else "—",
        "equipamento": str(ch.equipamento),
        "tecnico": (ch.tecnico.get_full_name() or ch.tecnico.get_username()) if ch.tecnico else "—",
        "aberto_em": ch.aberto_em,
        "encerrado_em": ch.encerrado_em,
        "tempo": tempo,
        "tempo_texto": formata_duracao(tempo),
        "no_prazo": tempo <= timedelta(hours=Chamado.HORAS_ATE_ATRASO),
    }


def sla(chamados_qs, inicio_dia, fim_dia, hoje=None):
    inicio, fim = _intervalo_horas(inicio_dia, fim_dia, hoje)
    prazo = timedelta(hours=Chamado.HORAS_ATE_ATRASO)

    encerrados = [
        _linha_chamado(ch, ch.encerrado_em - ch.aberto_em)
        for ch in chamados_qs.filter(
            status=Chamado.Status.ENCERRADO,
            encerrado_em__gte=inicio, encerrado_em__lt=fim,
        )
    ]
    # Em aberto no fim do período: abertos antes do corte e ainda não
    # encerrados naquele momento (podem ter sido encerrados depois).
    em_aberto = [
        _linha_chamado(ch, fim - ch.aberto_em)
        for ch in chamados_qs.filter(aberto_em__lt=fim).filter(
            Q(encerrado_em__isnull=True) | Q(encerrado_em__gte=fim)
        ).exclude(status=Chamado.Status.ENCERRADO, encerrado_em__isnull=True)
    ]
    encerrados.sort(key=lambda linha: linha["encerrado_em"])
    em_aberto.sort(key=lambda linha: -linha["tempo"])

    no_prazo = sum(1 for linha in encerrados if linha["no_prazo"])
    media = (
        sum((linha["tempo"] for linha in encerrados), timedelta()) / len(encerrados)
        if encerrados else None
    )
    media_aberto = (
        sum((linha["tempo"] for linha in em_aberto), timedelta()) / len(em_aberto)
        if em_aberto else None
    )
    return {
        "prazo_horas": Chamado.HORAS_ATE_ATRASO,
        "encerrados": encerrados,
        "em_aberto": em_aberto,
        "qtd_encerrados": len(encerrados),
        "qtd_em_aberto": len(em_aberto),
        "abertos_atrasados": sum(1 for linha in em_aberto if linha["tempo"] > prazo),
        "no_prazo": no_prazo,
        "fora_do_prazo": len(encerrados) - no_prazo,
        "percentual": (no_prazo / len(encerrados) * 100) if encerrados else None,
        "media": media,
        "media_texto": formata_duracao(media),
        "media_aberto_texto": formata_duracao(media_aberto),
    }


# ----- Painel completo -----

def montar(de, ate=None, cliente=None, hoje=None):
    """O painel do período de `de` a `ate`, cada um (ano, mês).

    Sem `ate`, é um mês só. Quem chama garante 1 a 12 meses (ver
    `periodo_valido`).
    """
    hoje = hoje or timezone.localdate()
    ate = ate or de
    inicio, fim = primeiro_dia(*de), ultimo_dia(*ate)
    referencia = min(fim, hoje)
    # A foto de comparação é a véspera do início do período
    ref_inicio = inicio - timedelta(days=1)
    meses = meses_entre(de, ate)

    locacoes = list(_locacoes(cliente))
    contratos = _contratos(cliente)
    chamados_qs = _chamados(cliente)

    recorrente = receita_recorrente(contratos, referencia)
    recorrente_anterior = receita_recorrente(contratos, ref_inicio)
    movimento_comercial = contratacoes_e_perdas(contratos, locacoes, inicio, fim)
    movimentos = movimentacao_equipamentos(locacoes, inicio, fim)
    indicador_sla = sla(chamados_qs, inicio, fim, hoje)
    maquinas_sem_contrato = sum(
        1 for loc in locacoes if not loc.contrato_id and vigente_em(loc, referencia)
    )

    manutencoes = Manutencao.objects.filter(data__gte=inicio, data__lte=fim)
    if cliente:
        # Manutenção não tem cliente: conta a da máquina que estava com ele.
        manutencoes = manutencoes.filter(equipamento__locacoes__cliente=cliente).distinct()
    custo_manutencao = manutencoes.aggregate(total=Sum("custo"))["total"]

    # Gráficos: os meses do período; com um mês só, os 12 meses até ele
    meses_grafico = meses if len(meses) > 1 else ultimos_meses(*ate)
    serie = []
    for a, m in meses_grafico:
        if primeiro_dia(a, m) > hoje:
            continue
        ini_mes, fim_mes = primeiro_dia(a, m), ultimo_dia(a, m)
        sla_mes = sla(chamados_qs, ini_mes, fim_mes, hoje)
        comercial_mes = contratacoes_e_perdas(contratos, locacoes, ini_mes, fim_mes)
        serie.append({
            "rotulo": f"{MESES_CURTOS[m - 1]}/{str(a)[2:]}",
            "recorrente": float(receita_recorrente(contratos, min(fim_mes, hoje))["valor"]),
            "nova": float(comercial_mes["novas"]["valor"]),
            "perdida": float(comercial_mes["perdas"]["valor"]),
            "media_horas": (
                round(sla_mes["media"].total_seconds() / 3600, 1)
                if sla_mes["media"] else None
            ),
            "instalados": sum(
                1 for loc in locacoes if entre(loc.data_inicio, ini_mes, fim_mes)
            ),
            "retirados": sum(
                1 for loc in locacoes
                if not loc.ativa and entre(loc.data_fim, ini_mes, fim_mes)
            ),
        })

    # Problemas de cadastro que mexem nos números — mostrados, não escondidos
    avisos = []
    if recorrente["sem_valor"]:
        nomes = ", ".join(c.identificacao for c in recorrente["sem_valor"][:5])
        mais = len(recorrente["sem_valor"]) - 5
        avisos.append(
            f"{len(recorrente['sem_valor'])} contrato(s) ativo(s) sem valor mensal: "
            f"{nomes}{f' e mais {mais}' if mais > 0 else ''}. Ficam fora da receita "
            "recorrente até o valor ser preenchido."
        )
    if maquinas_sem_contrato:
        avisos.append(
            f"{maquinas_sem_contrato} máquina(s) locada(s) sem contrato vinculado (muitas "
            "vieram da importação por PDF). A receita delas não aparece no painel, porque "
            "a receita sai do valor dos contratos."
        )
    if movimentos["instalados_suspeitos"]:
        avisos.append(
            f"{movimentos['instalados_suspeitos']} instalação(ões) {'do mês' if len(meses) == 1 else 'do período'} com valor R$ 0,00 e "
            "sem contrato. Se vieram da importação por PDF, a data de início é a da "
            "importação, não a da instalação real."
        )
    sem_data_fim = sum(1 for loc in locacoes if not loc.ativa and not loc.data_fim)
    if sem_data_fim:
        avisos.append(
            f"{sem_data_fim} locação(ões) encerrada(s) sem data de término: ficam fora "
            "das retiradas, porque não dá para saber quando terminaram."
        )
    if movimento_comercial["novas"]["sem_valor"]:
        avisos.append(
            f"{movimento_comercial['novas']['sem_valor']} contrato(s) novo(s) sem valor mensal: "
            "entram na contagem, mas não no valor das novas contratações."
        )
    if movimento_comercial["aditivos_sem_base"]:
        nomes = ", ".join(
            f"Aditivo {a.numero} ({_nome_cliente(a.contrato)})"
            for a in movimento_comercial["aditivos_sem_base"]
        )
        avisos.append(
            f"Não deu para calcular quanto mudou o valor de: {nomes}. O contrato não tem "
            "valor mensal de antes do aditivo."
        )

    return {
        "de": de,
        "ate": ate,
        "inicio": inicio,
        "fim": fim,
        "qtd_meses": len(meses),
        "um_mes": len(meses) == 1,
        # "no mês" / "no período", para os textos da tela
        "no_periodo": "no mês" if len(meses) == 1 else "no período",
        "rotulo": rotulo_periodo(de, ate),
        "referencia": referencia,
        "ref_inicio": ref_inicio,
        "em_andamento": referencia < fim,
        "recorrente": recorrente,
        "recorrente_anterior": recorrente_anterior,
        "recorrente_variacao": variacao_percentual(
            recorrente["valor"], recorrente_anterior["valor"]
        ),
        "contratos_ativos": recorrente["contratos"],
        "novas": movimento_comercial["novas"],
        "perdas": movimento_comercial["perdas"],
        "movimentos": movimentos,
        "sla": indicador_sla,
        "custo_manutencao": custo_manutencao,
        "serie": serie,
        "avisos": avisos,
    }
