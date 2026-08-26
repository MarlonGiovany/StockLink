import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    AditivoForm,
    ClienteForm,
    ContratoForm,
    EquipamentoForm,
    FornecedorForm,
    LocacaoForm,
    ManutencaoForm,
    ProdutoForm,
)
from .models import (
    Aditivo,
    Cliente,
    Contrato,
    Equipamento,
    Fornecedor,
    Locacao,
    Movimentacao,
    Produto,
)


def registrar_movimentacao(equipamento, tipo, descricao, usuario):
    """Cria um registro no histórico de movimentações (append-only)."""
    Movimentacao.objects.create(
        equipamento=equipamento,
        tipo=tipo,
        descricao=descricao,
        usuario=usuario if usuario and usuario.is_authenticated else None,
    )


@login_required
def equipamento_lista(request):
    """Abre no painel de produtos. Só mostra a lista corrida depois que o
    usuário escolhe um produto, clica em "Todos" ou faz uma busca."""
    termo = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    produto_param = request.GET.get("produto", "").strip()

    # Painel inicial: um botão por produto, com a quantidade de cada um
    if not produto_param and not termo and not status:
        produtos = (
            Produto.objects.filter(ativo=True)
            .annotate(qtd=Count("equipamentos"))
        )
        return render(
            request, "inventario/equipamento_produtos.html",
            {
                "produtos": produtos,
                "total_geral": Equipamento.objects.count(),
                "sem_produto": Equipamento.objects.filter(
                    produto__isnull=True
                ).count(),
            },
        )

    equipamentos = Equipamento.objects.select_related("produto")
    produto_atual = None
    if produto_param == "sem":
        equipamentos = equipamentos.filter(produto__isnull=True)
    elif produto_param and produto_param != "todos":
        produto_atual = get_object_or_404(Produto, pk=produto_param)
        equipamentos = equipamentos.filter(produto=produto_atual)

    if termo:
        equipamentos = equipamentos.filter(
            Q(marca__icontains=termo)
            | Q(modelo__icontains=termo)
            | Q(numero_serie__icontains=termo)
            | Q(numero_patrimonio__icontains=termo)
            | Q(local__icontains=termo)
            | Q(produto__nome__icontains=termo)
        )
    if status:
        equipamentos = equipamentos.filter(status=status)

    contexto = {
        "equipamentos": equipamentos,
        "termo": termo,
        "status_atual": status,
        "status_choices": Equipamento.Status.choices,
        "total": equipamentos.count(),
        "produto_atual": produto_atual,
        "produto_param": produto_param,
    }
    return render(request, "inventario/equipamento_lista.html", contexto)


@login_required
def equipamento_detalhe(request, pk):
    equipamento = get_object_or_404(Equipamento, pk=pk)
    locacao_ativa = equipamento.locacao_ativa

    # Contratos que já existem para o cliente desta locação — é a lista que
    # aparece no "vincular a contrato existente", para não duplicar contrato.
    contratos_do_cliente = Contrato.objects.none()
    if locacao_ativa and locacao_ativa.cliente_id:
        contratos_do_cliente = (
            Contrato.objects
            .filter(cliente_id=locacao_ativa.cliente_id)
            .annotate(qtd_maquinas=Count("locacoes"))
            .order_by("-data_contrato", "-id")
        )
        if locacao_ativa.contrato_id:
            contratos_do_cliente = contratos_do_cliente.exclude(
                pk=locacao_ativa.contrato_id
            )

    contexto = {
        "equipamento": equipamento,
        "manutencoes": equipamento.manutencoes.all(),
        "locacoes": equipamento.locacoes.all(),
        "movimentacoes": equipamento.movimentacoes.all(),
        "locacao_ativa": locacao_ativa,
        "contratos_do_cliente": contratos_do_cliente,
    }
    return render(request, "inventario/equipamento_detalhe.html", contexto)


def contexto_equipamento_form(form, titulo):
    """Contexto comum das telas de novo/editar equipamento.

    `produtos_config_json` diz ao template quais produtos abrem os campos de
    processador / RAM / armazenamento.
    """
    ids_com_config = list(
        Produto.objects.filter(ativo=True, pede_configuracao=True)
        .values_list("id", flat=True)
    )
    return {
        "form": form,
        "titulo": titulo,
        "produtos_config_json": json.dumps(ids_com_config),
        "campos_configuracao": EquipamentoForm.CAMPOS_CONFIGURACAO,
        "pode_add_produto": True,
    }


@login_required
@permission_required("inventario.add_equipamento", raise_exception=True)
def equipamento_novo(request):
    if request.method == "POST":
        form = EquipamentoForm(request.POST)
        if form.is_valid():
            equipamento = form.save()
            registrar_movimentacao(
                equipamento,
                Movimentacao.Tipo.CADASTRO,
                f"{equipamento.produto or 'Equipamento'} cadastrado em "
                f"'{equipamento.local or 'sem local'}'.",
                request.user,
            )
            messages.success(request, "Equipamento cadastrado com sucesso.")
            return redirect("equipamento_detalhe", pk=equipamento.pk)
    else:
        # Vindo do painel de produtos (?produto=<id>), já deixa escolhido
        inicial = {}
        produto_id = request.GET.get("produto")
        if produto_id and Produto.objects.filter(pk=produto_id, ativo=True).exists():
            inicial["produto"] = produto_id
        form = EquipamentoForm(initial=inicial)
    return render(
        request, "inventario/equipamento_form.html",
        contexto_equipamento_form(form, "Novo equipamento"),
    )


@login_required
@permission_required("inventario.add_produto", raise_exception=True)
def produto_novo(request):
    """Cadastra um produto novo na lista.

    Chamado por fetch() a partir do botão "+ Adicionar novo produto" da tela
    de cadastro de equipamento — responde JSON para o produto já aparecer
    escolhido sem recarregar a página e sem perder o que já foi digitado.
    Sem JavaScript, cai na página normal de formulário.
    """
    pede_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if request.method == "POST":
        form = ProdutoForm(request.POST)
        if form.is_valid():
            produto = form.save()
            if pede_json:
                return JsonResponse({
                    "ok": True,
                    "id": produto.pk,
                    "nome": produto.nome,
                    "pede_configuracao": produto.pede_configuracao,
                })
            messages.success(request, f'Produto "{produto.nome}" adicionado.')
            return redirect(
                f"{reverse('equipamento_novo')}?produto={produto.pk}"
            )
        if pede_json:
            erros = [e for lista in form.errors.values() for e in lista]
            return JsonResponse(
                {"ok": False, "erro": erros[0] if erros else "Não foi possível salvar."},
                status=400,
            )
    else:
        form = ProdutoForm()

    return render(
        request, "inventario/cadastro_form.html",
        {"form": form, "titulo": "Novo produto", "voltar": "equipamento_lista"},
    )


@login_required
@permission_required("inventario.change_equipamento", raise_exception=True)
def equipamento_editar(request, pk):
    equipamento = get_object_or_404(Equipamento, pk=pk)
    local_antigo = equipamento.local
    status_antigo = equipamento.status

    if request.method == "POST":
        form = EquipamentoForm(request.POST, instance=equipamento)
        if form.is_valid():
            equipamento = form.save()
            if local_antigo != equipamento.local:
                registrar_movimentacao(
                    equipamento, Movimentacao.Tipo.LOCAL,
                    f"Localização: '{local_antigo or '—'}' → '{equipamento.local or '—'}'.",
                    request.user,
                )
            if status_antigo != equipamento.status:
                registrar_movimentacao(
                    equipamento, Movimentacao.Tipo.STATUS,
                    f"Status: '{status_antigo}' → '{equipamento.status}'.",
                    request.user,
                )
            registrar_movimentacao(
                equipamento, Movimentacao.Tipo.EDICAO,
                "Dados do equipamento editados.", request.user,
            )
            messages.success(request, "Equipamento atualizado.")
            return redirect("equipamento_detalhe", pk=equipamento.pk)
    else:
        form = EquipamentoForm(instance=equipamento)
    return render(
        request, "inventario/equipamento_form.html",
        contexto_equipamento_form(form, f"Editar — {equipamento}"),
    )


@login_required
@permission_required("inventario.delete_equipamento", raise_exception=True)
def equipamento_excluir(request, pk):
    equipamento = get_object_or_404(Equipamento, pk=pk)
    if request.method == "POST":
        nome = str(equipamento)
        equipamento.delete()
        messages.success(request, f"Equipamento '{nome}' removido.")
        return redirect("equipamento_lista")
    return render(
        request, "inventario/equipamento_excluir.html", {"equipamento": equipamento}
    )


@login_required
@permission_required("inventario.add_manutencao", raise_exception=True)
def manutencao_nova(request, pk):
    equipamento = get_object_or_404(Equipamento, pk=pk)
    if request.method == "POST":
        form = ManutencaoForm(request.POST)
        if form.is_valid():
            manutencao = form.save(commit=False)
            manutencao.equipamento = equipamento
            manutencao.registrado_por = request.user
            manutencao.save()
            registrar_movimentacao(
                equipamento, Movimentacao.Tipo.MANUTENCAO,
                f"Manutenção registrada: {manutencao.descricao[:120]}",
                request.user,
            )
            messages.success(request, "Manutenção registrada.")
            return redirect("equipamento_detalhe", pk=equipamento.pk)
    else:
        form = ManutencaoForm()
    return render(
        request, "inventario/manutencao_form.html",
        {"form": form, "equipamento": equipamento},
    )


@login_required
@permission_required("inventario.add_locacao", raise_exception=True)
def locacao_nova(request, pk):
    equipamento = get_object_or_404(Equipamento, pk=pk)
    if request.method == "POST":
        form = LocacaoForm(request.POST)
        if form.is_valid():
            locacao = form.save(commit=False)
            locacao.equipamento = equipamento
            locacao.save()
            if locacao.ativa:
                equipamento.status = Equipamento.Status.LOCADO
                equipamento.save(update_fields=["status"])
            vinculo = (
                f" Vinculado ao contrato Nº {locacao.contrato.numero}."
                if locacao.contrato else ""
            )
            registrar_movimentacao(
                equipamento, Movimentacao.Tipo.LOCACAO,
                f"Locado para {locacao.cliente} por R$ {locacao.valor} "
                f"(início {locacao.data_inicio:%d/%m/%Y}).{vinculo}",
                request.user,
            )
            messages.success(request, "Locação registrada.")
            return redirect("equipamento_detalhe", pk=equipamento.pk)
    else:
        form = LocacaoForm()
    return render(
        request, "inventario/locacao_form.html",
        {"form": form, "equipamento": equipamento},
    )


@login_required
@permission_required("inventario.change_locacao", raise_exception=True)
def locacao_vincular_contrato(request, pk):
    """Pendura uma locação já registrada num contrato que JÁ EXISTE.

    É o que evita duplicar contrato quando o mesmo cliente aluga mais de uma
    máquina: todas as locações dele apontam para o mesmo contrato.
    """
    locacao = get_object_or_404(Locacao, pk=pk)
    equipamento = locacao.equipamento

    if request.method != "POST":
        return redirect("equipamento_detalhe", pk=equipamento.pk)

    contrato_id = request.POST.get("contrato", "").strip()
    if not contrato_id:
        messages.error(request, "Escolha um contrato para vincular.")
        return redirect("equipamento_detalhe", pk=equipamento.pk)

    contrato = get_object_or_404(Contrato, pk=contrato_id)

    # Mesma trava do formulário: contrato de outro cliente, não.
    if contrato.cliente_id and contrato.cliente_id != locacao.cliente_id:
        messages.error(
            request,
            f'O contrato Nº {contrato.numero} é do cliente "{contrato.cliente}" '
            f'e esta locação é de "{locacao.cliente}".',
        )
        return redirect("equipamento_detalhe", pk=equipamento.pk)

    anterior = locacao.contrato
    locacao.contrato = contrato
    locacao.save(update_fields=["contrato"])

    if anterior and anterior.pk != contrato.pk:
        texto = (f"Contrato da locação alterado: Nº {anterior.numero} → "
                 f"Nº {contrato.numero}.")
    else:
        texto = f"Locação vinculada ao contrato Nº {contrato.numero}."
    registrar_movimentacao(
        equipamento, Movimentacao.Tipo.LOCACAO, texto, request.user
    )

    messages.success(
        request,
        f"Locação vinculada ao contrato Nº {contrato.numero} "
        f"({contrato.locacoes.count()} máquina(s) neste contrato).",
    )
    return redirect("equipamento_detalhe", pk=equipamento.pk)


@login_required
@permission_required("inventario.change_locacao", raise_exception=True)
def locacao_encerrar(request, pk):
    locacao = get_object_or_404(Locacao, pk=pk, ativa=True)
    equipamento = locacao.equipamento
    if request.method == "POST":
        locacao.ativa = False
        if not locacao.data_fim:
            locacao.data_fim = timezone.now().date()
        locacao.save()
        equipamento.status = Equipamento.Status.DISPONIVEL
        equipamento.save(update_fields=["status"])
        registrar_movimentacao(
            equipamento, Movimentacao.Tipo.DEVOLUCAO,
            f"Devolução de {locacao.cliente} em {locacao.data_fim:%d/%m/%Y}.",
            request.user,
        )
        messages.success(request, "Devolução registrada.")
        return redirect("equipamento_detalhe", pk=equipamento.pk)
    return render(
        request, "inventario/locacao_encerrar.html",
        {"locacao": locacao, "equipamento": equipamento},
    )


# ----- Cadastros auxiliares (fornecedores e clientes) -----

@login_required
def fornecedor_lista(request):
    return render(
        request, "inventario/fornecedor_lista.html",
        {"fornecedores": Fornecedor.objects.all()},
    )


@login_required
@permission_required("inventario.add_fornecedor", raise_exception=True)
def fornecedor_novo(request):
    if request.method == "POST":
        form = FornecedorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Fornecedor cadastrado.")
            return redirect("fornecedor_lista")
    else:
        form = FornecedorForm()
    return render(
        request, "inventario/cadastro_form.html",
        {"form": form, "titulo": "Novo fornecedor", "voltar": "fornecedor_lista"},
    )


@login_required
def cliente_lista(request):
    return render(
        request, "inventario/cliente_lista.html",
        {"clientes": Cliente.objects.all()},
    )


@login_required
@permission_required("inventario.add_cliente", raise_exception=True)
def cliente_novo(request):
    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Cliente cadastrado.")
            return redirect("cliente_lista")
    else:
        form = ClienteForm()
    return render(
        request, "inventario/cadastro_form.html",
        {"form": form, "titulo": "Novo cliente", "voltar": "cliente_lista"},
    )


# ----- Contratos -----

ORDENS_CONTRATO = {
    "data_desc": ("-data_contrato", "Data (mais recentes)"),
    "data_asc": ("data_contrato", "Data (mais antigos)"),
    "numero_asc": ("numero", "Número (crescente)"),
    "numero_desc": ("-numero", "Número (decrescente)"),
}


@login_required
def contrato_lista(request):
    termo = request.GET.get("q", "").strip()
    ordenar = request.GET.get("ordenar", "data_desc")
    de = request.GET.get("de", "").strip()
    ate = request.GET.get("ate", "").strip()

    contratos = (
        Contrato.objects.select_related("cliente")
        .annotate(qtd_maquinas=Count("locacoes"))
    )
    if termo:
        contratos = contratos.filter(
            Q(numero__icontains=termo)
            | Q(titulo__icontains=termo)
            | Q(cliente__nome__icontains=termo)
        )
    if de:
        contratos = contratos.filter(data_contrato__gte=de)
    if ate:
        contratos = contratos.filter(data_contrato__lte=ate)

    campo = ORDENS_CONTRATO.get(ordenar, ORDENS_CONTRATO["data_desc"])[0]
    contratos = contratos.order_by(campo, "-id")

    contexto = {
        "contratos": contratos,
        "termo": termo,
        "ordenar": ordenar,
        "de": de,
        "ate": ate,
        "ordens": ORDENS_CONTRATO,
        "total": contratos.count(),
    }
    return render(request, "inventario/contrato_lista.html", contexto)


@login_required
@permission_required("inventario.add_contrato", raise_exception=True)
def contrato_novo(request):
    # Quando vem da ficha de um equipamento locado (?locacao=<pk>),
    # já puxamos o cliente/equipamento e vinculamos o contrato à locação.
    locacao_id = request.GET.get("locacao")
    locacao = Locacao.objects.filter(pk=locacao_id).first() if locacao_id else None

    if request.method == "POST":
        form = ContratoForm(request.POST, request.FILES)
        if form.is_valid():
            contrato = form.save(commit=False)
            contrato.criado_por = request.user
            contrato.save()
            if locacao:
                locacao.contrato = contrato
                locacao.save(update_fields=["contrato"])
                messages.success(
                    request,
                    f"Contrato {contrato.numero} anexado e vinculado à locação de "
                    f"{locacao.equipamento}.",
                )
                return redirect("equipamento_detalhe", pk=locacao.equipamento.pk)
            messages.success(request, "Contrato anexado com sucesso.")
            return redirect("contrato_lista")
    else:
        initial = {}
        if locacao:
            initial = {
                "cliente": locacao.cliente_id,
                "titulo": f"Locação — {locacao.equipamento}",
            }
        form = ContratoForm(initial=initial)
    return render(
        request, "inventario/contrato_form.html",
        {"form": form, "titulo": "Anexar contrato", "locacao": locacao},
    )


@login_required
@permission_required("inventario.change_contrato", raise_exception=True)
def contrato_editar(request, pk):
    contrato = get_object_or_404(Contrato, pk=pk)
    if request.method == "POST":
        form = ContratoForm(request.POST, request.FILES, instance=contrato)
        if form.is_valid():
            form.save()
            messages.success(request, "Contrato atualizado.")
            return redirect("contrato_lista")
    else:
        form = ContratoForm(instance=contrato)
    return render(
        request, "inventario/contrato_form.html",
        {"form": form, "titulo": f"Editar contrato {contrato.numero}", "contrato": contrato},
    )


@login_required
@permission_required("inventario.delete_contrato", raise_exception=True)
def contrato_excluir(request, pk):
    contrato = get_object_or_404(Contrato, pk=pk)
    if request.method == "POST":
        numero = contrato.numero
        if contrato.arquivo:
            contrato.arquivo.delete(save=False)
        contrato.delete()
        messages.success(request, f"Contrato {numero} excluído.")
        return redirect("contrato_lista")
    return render(
        request, "inventario/contrato_excluir.html", {"contrato": contrato}
    )


@login_required
def contrato_detalhe(request, pk):
    contrato = get_object_or_404(Contrato, pk=pk)
    aditivos = list(contrato.aditivos.all())
    ultimo_id = aditivos[-1].id if aditivos else None
    locacoes = (
        contrato.locacoes
        .select_related("equipamento", "equipamento__produto", "cliente")
        .order_by("-ativa", "-data_inicio")
    )
    contexto = {
        "contrato": contrato,
        "aditivos": aditivos,
        "ultimo_aditivo_id": ultimo_id,
        "locacoes": locacoes,
        "qtd_maquinas": locacoes.count(),
    }
    return render(request, "inventario/contrato_detalhe.html", contexto)


@login_required
@permission_required("inventario.add_aditivo", raise_exception=True)
def aditivo_novo(request, pk):
    contrato = get_object_or_404(Contrato, pk=pk)
    if request.method == "POST":
        form = AditivoForm(request.POST, request.FILES)
        if form.is_valid():
            aditivo = form.save(commit=False)
            proximo = (contrato.aditivos.aggregate(m=Max("numero"))["m"] or 0) + 1
            aditivo.contrato = contrato
            aditivo.numero = proximo
            aditivo.criado_por = request.user
            aditivo.save()
            messages.success(request, f"Aditivo {proximo} registrado.")
            return redirect("contrato_detalhe", pk=contrato.pk)
    else:
        form = AditivoForm()
    return render(
        request, "inventario/aditivo_form.html",
        {"form": form, "contrato": contrato},
    )


@login_required
@permission_required("inventario.delete_aditivo", raise_exception=True)
def aditivo_excluir(request, pk):
    aditivo = get_object_or_404(Aditivo, pk=pk)
    contrato = aditivo.contrato
    # Só permite excluir o último aditivo, para não furar a sequência/totais
    ultimo = contrato.aditivos.order_by("-numero").first()
    if aditivo.pk != ultimo.pk:
        messages.error(
            request,
            "Só é possível excluir o aditivo mais recente do contrato.",
        )
        return redirect("contrato_detalhe", pk=contrato.pk)
    if request.method == "POST":
        numero = aditivo.numero
        if aditivo.arquivo:
            aditivo.arquivo.delete(save=False)
        aditivo.delete()
        messages.success(request, f"Aditivo {numero} excluído.")
        return redirect("contrato_detalhe", pk=contrato.pk)
    return render(
        request, "inventario/aditivo_excluir.html",
        {"aditivo": aditivo, "contrato": contrato},
    )
