import json
import os
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, IntegerField, Max, Q, Sum, Value, When
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .forms import (
    AditivoEdicaoForm,
    AditivoForm,
    ChamadoAberturaForm,
    ChamadoAnexoForm,
    ChamadoEncerramentoForm,
    ClienteForm,
    ContratoForm,
    EquipamentoForm,
    FornecedorForm,
    LocacaoForm,
    ManutencaoForm,
    ProdutoForm,
    ValorEmLoteForm,
)
from .models import (
    Aditivo,
    Chamado,
    Cliente,
    Contrato,
    Equipamento,
    Fornecedor,
    Locacao,
    Movimentacao,
    Produto,
    formata_duracao,
)
from .permissoes import (
    AREAS,
    PERFIS,
    VER_CONTRATOS,
    VER_PDFS,
    aplica_perfil,
    exige_analista,
    eh_analista,
    exige_area,
    perfil_do_usuario,
    usuario_analista,
    ve_todos_os_chamados,
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
            .annotate(
                qtd_maquinas=Count("locacoes", filter=Q(locacoes__ativa=True))
            )
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
    locacao_ativa = equipamento.locacao_ativa
    if request.method == "POST":
        if locacao_ativa:
            # Revalida no servidor: o botão de excluir não é escondido quando
            # o equipamento está locado, então um POST ainda conseguiria
            # remover uma máquina que está com um cliente no momento.
            messages.error(
                request,
                f"Este equipamento está locado para {locacao_ativa.cliente} e "
                f"não pode ser excluído. Encerre a locação antes de remover "
                f"o equipamento.",
            )
            return redirect("equipamento_detalhe", pk=equipamento.pk)
        nome = str(equipamento)
        equipamento.delete()
        messages.success(request, f"Equipamento '{nome}' removido.")
        return redirect("equipamento_lista")
    return render(
        request, "inventario/equipamento_excluir.html",
        {"equipamento": equipamento, "locacao_ativa": locacao_ativa},
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
            locacao_ativa = equipamento.locacao_ativa
            if form.cleaned_data["ativa"] and locacao_ativa:
                # Revalida no servidor: a tela esconde o botão quando já há uma
                # locação ativa, mas um POST direto ainda conseguiria criar uma
                # segunda para o mesmo equipamento.
                messages.error(
                    request,
                    f"Este equipamento já está locado para "
                    f"{locacao_ativa.cliente}. Encerre a locação atual antes "
                    f"de registrar uma nova.",
                )
            else:
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
        f"({contrato.maquinas_ativas} máquina(s) neste contrato).",
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
    """Lista de clientes, com busca pelo nome."""
    termo = request.GET.get("q", "").strip()
    clientes = Cliente.objects.all()
    if termo:
        clientes = clientes.filter(nome__icontains=termo)
    return render(
        request, "inventario/cliente_lista.html",
        {"clientes": clientes, "termo": termo, "total": clientes.count()},
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
@exige_area(VER_CONTRATOS)
def contrato_lista(request):
    termo = request.GET.get("q", "").strip()
    ordenar = request.GET.get("ordenar", "data_desc")
    de = request.GET.get("de", "").strip()
    ate = request.GET.get("ate", "").strip()

    contratos = (
        Contrato.objects.select_related("cliente")
        # Máquina devolvida (locação encerrada) não entra no total do contrato
        .annotate(
            qtd_maquinas=Count("locacoes", filter=Q(locacoes__ativa=True))
        )
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
    contratos = list(contratos.order_by(campo, "-id"))

    contexto = {
        "contratos": contratos,
        "termo": termo,
        "ordenar": ordenar,
        "de": de,
        "ate": ate,
        "ordens": ORDENS_CONTRATO,
        "total": len(contratos),
        # Renovação automática de 1 ano — aviso só pra quem está perto do
        # aniversário (ver Contrato.DIAS_ATE_RENOVACAO), calculado na hora.
        "qtd_renovando": sum(1 for c in contratos if c.renovacao_proxima),
    }
    return render(request, "inventario/contrato_lista.html", contexto)


def _reais(valor):
    """1250.5 -> "1.250,50" — para as mensagens saírem no padrão brasileiro."""
    return f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


@login_required
@permission_required("inventario.change_locacao", raise_exception=True)
@exige_area(VER_CONTRATOS)
def locacao_valor_em_lote(request, pk):
    """Aplica um mesmo valor de locação a várias máquinas do contrato de uma vez.

    Só mexe nas locações **ativas deste contrato**: a lista de ids vem do
    formulário, mas é filtrada pelo contrato aqui no servidor — senão daria
    para alterar a locação de outro cliente mexendo no HTML da página. E
    locação encerrada fica de fora porque é registro histórico.

    Cada máquina alterada ganha uma linha na movimentação, para o histórico
    continuar contando de onde veio cada valor.
    """
    contrato = get_object_or_404(Contrato, pk=pk)
    destino = redirect("contrato_detalhe", pk=contrato.pk)
    if request.method != "POST":
        return destino

    form = ValorEmLoteForm(request.POST)
    locacoes = list(
        contrato.locacoes
        .filter(pk__in=request.POST.getlist("locacoes"), ativa=True)
        .select_related("equipamento")
    )

    if not locacoes:
        messages.error(
            request,
            "Marque ao menos uma máquina ativa para aplicar o valor.",
        )
        return destino
    if not form.is_valid():
        # Não assume qual campo falhou — hoje só existe "valor", mas erros de
        # validação futuros (ou um clean() sem campo associado) não podem
        # estourar KeyError aqui.
        primeiro_erro = next(iter(form.errors.values()), ["Valor inválido."])[0]
        messages.error(request, primeiro_erro)
        return destino

    valor = form.cleaned_data["valor"]
    alteradas = []
    for locacao in locacoes:
        if locacao.valor == valor:
            continue
        anterior = locacao.valor
        locacao.valor = valor
        locacao.save(update_fields=["valor"])
        registrar_movimentacao(
            locacao.equipamento,
            Movimentacao.Tipo.LOCACAO,
            f"Valor da locação: R$ {_reais(anterior)} → R$ {_reais(valor)} "
            f"(alteração em lote, contrato Nº {contrato.numero}).",
            request.user,
        )
        alteradas.append(locacao)

    if alteradas:
        messages.success(
            request,
            f"R$ {_reais(valor)} aplicado a {len(alteradas)} "
            f"máquina{'s' if len(alteradas) > 1 else ''} "
            f"do contrato Nº {contrato.numero}."
            + (f" As outras {len(locacoes) - len(alteradas)} já estavam "
               f"com esse valor." if len(locacoes) > len(alteradas) else "")
        )
    else:
        messages.info(
            request,
            f"Nada a mudar: as {len(locacoes)} máquinas marcadas já estavam "
            f"com R$ {_reais(valor)}.",
        )
    return destino


@login_required
@permission_required("inventario.add_contrato", raise_exception=True)
@exige_area(VER_CONTRATOS)
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
@exige_area(VER_CONTRATOS)
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
@exige_area(VER_CONTRATOS)
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
@exige_area(VER_CONTRATOS)
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
        # O contador mostra só o que está ativo hoje; a tabela abaixo continua
        # listando também as locações encerradas, como histórico do contrato.
        "qtd_maquinas": locacoes.filter(ativa=True).count(),
        "qtd_encerradas": locacoes.filter(ativa=False).count(),
        # Soma o valor só das locações ativas — mesmo recorte do contador acima.
        # Recalculado a cada carregamento da página, nunca fica desatualizado.
        "valor_total_maquinas": locacoes.filter(ativa=True).aggregate(
            total=Sum("valor")
        )["total"],
        "valor_lote_form": ValorEmLoteForm(),
    }
    return render(request, "inventario/contrato_detalhe.html", contexto)


@login_required
@permission_required("inventario.add_aditivo", raise_exception=True)
@exige_area(VER_CONTRATOS)
def aditivo_novo(request, pk):
    contrato = get_object_or_404(Contrato, pk=pk)
    if request.method == "POST":
        form = AditivoForm(request.POST, request.FILES)
        if form.is_valid():
            equipamentos = list(form.cleaned_data.get("equipamentos") or [])

            if equipamentos and not contrato.cliente_id:
                form.add_error(
                    None,
                    "Este contrato ainda não tem cliente definido. Edite o "
                    "contrato e escolha o cliente antes de incluir máquinas "
                    "por aditivo.",
                )
            else:
                # Revalida no servidor: a lista pode ter ficado desatualizada
                # entre abrir a tela e salvar (outra pessoa aditivou a mesma
                # máquina nesse meio-tempo).
                ids = [e.pk for e in equipamentos]
                disponiveis_ids = set(
                    Equipamento.objects.filter(
                        pk__in=ids, status=Equipamento.Status.DISPONIVEL
                    ).values_list("pk", flat=True)
                )
                indisponiveis = [e for e in equipamentos if e.pk not in disponiveis_ids]
                if indisponiveis:
                    nomes = ", ".join(
                        f"INF-{e.numero_patrimonio}" for e in indisponiveis
                    )
                    form.add_error(
                        "equipamentos",
                        f"Estas máquinas deixaram de estar disponíveis enquanto "
                        f"o formulário estava aberto: {nomes}. Atualize a "
                        f"página e tente de novo.",
                    )
                else:
                    # Cada máquina marcada tem seu próprio campo de valor no
                    # POST (valor_equip_<id>) — o preço pode variar de máquina
                    # pra máquina dentro do mesmo aditivo, então não dá pra
                    # aplicar um valor único a todas.
                    valores = {}
                    erro_valor = None
                    for equipamento in equipamentos:
                        bruto = request.POST.get(
                            f"valor_equip_{equipamento.pk}", ""
                        ).strip().replace(",", ".")
                        try:
                            valor = Decimal(bruto)
                            if valor < 0:
                                raise InvalidOperation
                        except (InvalidOperation, ValueError):
                            erro_valor = (
                                f"Informe um valor válido (0 ou maior) para "
                                f"a máquina INF-{equipamento.numero_patrimonio}."
                            )
                            break
                        valores[equipamento.pk] = valor

                    if erro_valor:
                        form.add_error("equipamentos", erro_valor)
                    else:
                        aditivo = form.save(commit=False)
                        aditivo.contrato = contrato
                        aditivo.criado_por = request.user
                        if equipamentos:
                            if not aditivo.descricao:
                                nomes = ", ".join(
                                    f"INF-{e.numero_patrimonio}" for e in equipamentos
                                )
                                aditivo.descricao = (
                                    f"{len(equipamentos)} máquina(s) incluída(s): {nomes}"
                                )
                            # Soma o valor real de cada máquina — elas podem
                            # ter preços diferentes entre si.
                            aditivo.valor = sum(valores.values())

                        # O número do aditivo é o próximo livre do contrato. Duas
                        # pessoas salvando ao mesmo tempo podem calcular o mesmo
                        # "próximo" antes de qualquer uma gravar — a constraint
                        # única barra a segunda, e ela tenta de novo com um
                        # número recalculado em vez de estourar erro 500.
                        proximo = None
                        salvo = False
                        for _tentativa in range(3):
                            try:
                                with transaction.atomic():
                                    proximo = (
                                        contrato.aditivos.aggregate(
                                            m=Max("numero")
                                        )["m"] or 0
                                    ) + 1
                                    aditivo.numero = proximo
                                    aditivo.save()

                                    for equipamento in equipamentos:
                                        valor = valores[equipamento.pk]
                                        Locacao.objects.create(
                                            equipamento=equipamento,
                                            cliente=contrato.cliente,
                                            contrato=contrato,
                                            aditivo=aditivo,
                                            valor=valor,
                                            data_inicio=aditivo.data,
                                            ativa=True,
                                        )
                                        equipamento.status = Equipamento.Status.LOCADO
                                        equipamento.save(update_fields=["status"])
                                        registrar_movimentacao(
                                            equipamento, Movimentacao.Tipo.LOCACAO,
                                            f"Locado para {contrato.cliente} por "
                                            f"R$ {_reais(valor)} via Aditivo "
                                            f"{proximo} do contrato "
                                            f"Nº {contrato.numero}.",
                                            request.user,
                                        )
                                salvo = True
                                break
                            except IntegrityError:
                                continue

                        if not salvo:
                            form.add_error(
                                None,
                                "Não foi possível registrar o aditivo agora "
                                "— outra pessoa salvou um aditivo neste "
                                "contrato ao mesmo tempo. Tente novamente.",
                            )
                        elif equipamentos:
                            messages.success(
                                request,
                                f"Aditivo {proximo} registrado com "
                                f"{len(equipamentos)} máquina(s) incluída(s).",
                            )
                            return redirect("contrato_detalhe", pk=contrato.pk)
                        else:
                            messages.success(request, f"Aditivo {proximo} registrado.")
                            return redirect("contrato_detalhe", pk=contrato.pk)
    else:
        form = AditivoForm()
    return render(
        request, "inventario/aditivo_form.html",
        {"form": form, "contrato": contrato},
    )


@login_required
@permission_required("inventario.change_aditivo", raise_exception=True)
@exige_area(VER_CONTRATOS)
def aditivo_editar(request, pk):
    """Corrige descrição, data, PDF e observações de um aditivo já salvo.

    As máquinas do aditivo não mudam por aqui (ver AditivoEdicaoForm).
    """
    aditivo = get_object_or_404(Aditivo.objects.select_related("contrato"), pk=pk)
    contrato = aditivo.contrato
    if request.method == "POST":
        form = AditivoEdicaoForm(request.POST, request.FILES, instance=aditivo)
        if form.is_valid():
            form.save()
            messages.success(request, f"Aditivo {aditivo.numero} atualizado.")
            return redirect("contrato_detalhe", pk=contrato.pk)
    else:
        form = AditivoEdicaoForm(instance=aditivo)
    return render(
        request, "inventario/aditivo_editar.html",
        {"form": form, "aditivo": aditivo, "contrato": contrato},
    )


@login_required
@permission_required("inventario.delete_aditivo", raise_exception=True)
@exige_area(VER_CONTRATOS)
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
    # Máquinas que este aditivo incluiu: excluir o aditivo desfaz a inclusão
    # delas também, senão ficariam "Locadas" num contrato sem nenhum aditivo
    # ou locação que explique por quê.
    locacoes = list(aditivo.locacoes.select_related("equipamento"))
    if request.method == "POST":
        numero = aditivo.numero
        with transaction.atomic():
            for locacao in locacoes:
                equipamento = locacao.equipamento
                locacao.delete()
                # Só devolve a máquina a Disponível se não sobrar outra
                # locação ativa dela — não deveria acontecer, mas por
                # segurança não mexe no status se sobrar alguma.
                if not equipamento.locacoes.filter(ativa=True).exists():
                    equipamento.status = Equipamento.Status.DISPONIVEL
                    equipamento.save(update_fields=["status"])
                registrar_movimentacao(
                    equipamento, Movimentacao.Tipo.EDICAO,
                    f"Inclusão desfeita: o Aditivo {numero} do contrato "
                    f"Nº {contrato.numero} foi excluído.",
                    request.user,
                )
            if aditivo.arquivo:
                aditivo.arquivo.delete(save=False)
            aditivo.delete()
        if locacoes:
            messages.success(
                request,
                f"Aditivo {numero} excluído — {len(locacoes)} máquina(s) "
                f"voltaram a ficar disponíveis.",
            )
        else:
            messages.success(request, f"Aditivo {numero} excluído.")
        return redirect("contrato_detalhe", pk=contrato.pk)
    return render(
        request, "inventario/aditivo_excluir.html",
        {"aditivo": aditivo, "contrato": contrato, "locacoes": locacoes},
    )


# ----- PDFs anexados (área restrita) -----

def _entregar_pdf(arquivo):
    """Devolve o PDF para abrir no navegador.

    Os PDFs não ficam mais numa URL pública: quem quiser abrir passa por aqui
    e o Django confere a permissão antes de entregar o arquivo.
    """
    if not arquivo:
        raise Http404("Nenhum PDF anexado.")
    try:
        return FileResponse(
            arquivo.open("rb"),
            content_type="application/pdf",
            filename=os.path.basename(arquivo.name),
        )
    except FileNotFoundError:
        raise Http404("O arquivo não está mais na pasta media.")


@login_required
@exige_area(VER_PDFS)
def contrato_pdf(request, pk):
    contrato = get_object_or_404(Contrato, pk=pk)
    return _entregar_pdf(contrato.arquivo)


@login_required
@exige_area(VER_PDFS)
def aditivo_pdf(request, pk):
    aditivo = get_object_or_404(Aditivo, pk=pk)
    return _entregar_pdf(aditivo.arquivo)


# ----- Usuários e permissões (só o Analista) -----

@login_required
@exige_analista
def permissoes_usuarios(request):
    """Tela onde o Analista escolhe o perfil de cada usuário e libera as
    áreas restritas.

    O Analista não aparece na lista de propósito: ele enxerga tudo e não teria
    como se tirar do próprio acesso.
    """
    analista = usuario_analista()
    usuarios = (
        get_user_model().objects
        .exclude(pk=analista.pk)
        .prefetch_related("user_permissions", "groups__permissions")
        .order_by("username")
    )
    permissoes = {
        codigo: Permission.objects.get(
            content_type__app_label="inventario", codename=codigo
        )
        for codigo, _, _ in AREAS
    }
    codigos_perfil = {codigo for codigo, _, _ in PERFIS}

    if request.method == "POST":
        alterados = 0
        for usuario in usuarios:
            grupos = {g.name for g in usuario.groups.all()}
            perfil = request.POST.get(f"perfil_{usuario.pk}", "")
            if perfil in codigos_perfil and perfil != perfil_do_usuario(usuario, grupos):
                aplica_perfil(usuario, perfil)
                alterados += 1
            for codigo, _, _ in AREAS:
                marcado = f"{codigo}_{usuario.pk}" in request.POST
                tinha = permissoes[codigo] in usuario.user_permissions.all()
                if marcado and not tinha:
                    usuario.user_permissions.add(permissoes[codigo])
                    alterados += 1
                elif not marcado and tinha:
                    usuario.user_permissions.remove(permissoes[codigo])
                    alterados += 1
        if alterados:
            messages.success(request, "Permissões salvas.")
        else:
            messages.info(request, "Nada mudou nas permissões.")
        return redirect("permissoes_usuarios")

    # Monta a tabela: uma linha por usuário, uma coluna por área
    linhas = []
    for usuario in usuarios:
        grupos = {g.name for g in usuario.groups.all()}
        do_grupo = {
            p.codename
            for grupo in usuario.groups.all()
            for p in grupo.permissions.all()
        }
        diretas = {p.codename for p in usuario.user_permissions.all()}
        linhas.append({
            "usuario": usuario,
            "perfil": perfil_do_usuario(usuario, grupos),
            "areas": [
                {
                    "codigo": codigo,
                    "marcado": codigo in diretas,
                    "via_grupo": codigo in do_grupo,
                }
                for codigo, _, _ in AREAS
            ],
        })

    return render(
        request, "inventario/permissoes.html",
        {"analista": analista, "linhas": linhas, "areas": AREAS, "perfis": PERFIS},
    )


@login_required
@exige_analista
def usuario_trocar_senha(request, pk):
    """O Analista define uma senha nova para quem esqueceu a sua.

    Usa o formulário padrão do Django: senha nova duas vezes e as mesmas
    regras de senha do sistema (tamanho mínimo, não pode ser comum, etc.).
    Trocar a senha desconecta a pessoa de onde ela estiver logada.

    A senha do próprio Analista não passa por aqui — ele troca a dele em
    /admin/, como sempre.
    """
    from django.contrib.auth.forms import SetPasswordForm

    usuario = get_object_or_404(get_user_model(), pk=pk)
    if usuario.pk == usuario_analista().pk:
        raise Http404
    if request.method == "POST":
        form = SetPasswordForm(usuario, request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Senha de {usuario.get_username()} alterada. Passe a senha "
                f"nova para a pessoa — ela vai precisar entrar de novo.",
            )
            return redirect("permissoes_usuarios")
    else:
        form = SetPasswordForm(usuario)
    for campo in form.fields.values():
        campo.widget.attrs.update({"class": "form-control", "autocomplete": "new-password"})
    return render(
        request, "inventario/usuario_trocar_senha.html",
        {"usuario": usuario, "form": form},
    )


# ----- Chamados e Ordem de Serviço -----

def _chamados_visiveis(user):
    """Os chamados que o usuário pode ver fora do painel.

    Técnico: só as OS designadas a ele. Recepção e superusuário: todas
    (ver `ve_todos_os_chamados`).
    """
    chamados = Chamado.objects.all()
    if not ve_todos_os_chamados(user):
        chamados = chamados.filter(tecnico=user)
    return chamados


def _confere_chamado_visivel(user, chamado):
    """403 para quem abre a OS de outro técnico (o painel mostra todas)."""
    if not ve_todos_os_chamados(user) and chamado.tecnico_id != user.pk:
        raise PermissionDenied


def _chamados_filtrados(request, status_padrao=None):
    """Aplica os filtros do painel de chamados e do histórico.

    Devolve (queryset, filtros) — `filtros` volta para o template deixar os
    campos preenchidos do jeito que o usuário escolheu.

    `status_padrao` é o status usado quando a pessoa **ainda não escolheu
    nada** — quando `status` não vem na URL. A distinção importa: o
    formulário sempre manda o campo, mesmo vazio, e vazio significa "quero
    todos, escolhi isso". Só o endereço pelado (`/chamados/`) cai no padrão.

    A lista usa isso para abrir mostrando só os chamados em aberto; o
    histórico não usa, porque histórico sem os encerrados não é histórico.
    """
    if "status" in request.GET:
        status = request.GET["status"].strip()
    else:
        status = status_padrao or ""
    tecnico_id = request.GET.get("tecnico", "").strip()
    cliente_id = request.GET.get("cliente", "").strip()
    de = request.GET.get("de", "").strip()
    ate = request.GET.get("ate", "").strip()

    chamados = _chamados_visiveis(request.user).select_related(
        "equipamento", "equipamento__produto", "tecnico", "cliente",
        "aberto_por", "encerrado_por",
    )
    if status:
        chamados = chamados.filter(status=status)
    if tecnico_id:
        chamados = chamados.filter(tecnico_id=tecnico_id)
    if cliente_id:
        chamados = chamados.filter(cliente_id=cliente_id)
    if de:
        chamados = chamados.filter(aberto_em__date__gte=de)
    if ate:
        chamados = chamados.filter(aberto_em__date__lte=ate)

    filtros = {
        "status": status,
        "tecnico": tecnico_id,
        "cliente": cliente_id,
        "de": de,
        "ate": ate,
        "status_choices": Chamado.Status.choices,
        "tecnicos": get_user_model().objects
            .filter(chamados_designados__isnull=False)
            .distinct().order_by("username"),
        # Só os clientes que já tiveram atendimento — um cliente sem chamado
        # na lista só levaria a um resultado vazio.
        "clientes": Cliente.objects
            .filter(chamados__isnull=False)
            .distinct().order_by("nome"),
    }
    return chamados, filtros


@login_required
def chamado_lista(request):
    """Painel de chamados: tudo que a recepção abriu, com filtros.

    Abre mostrando **só os chamados em aberto** — que é o que alguém quer ver
    ao entrar aqui. Os encerrados só se acumulam, e depois de alguns meses
    eram eles que dominavam a tela. Ficam a um clique de distância, no botão
    do topo.
    """
    chamados, filtros = _chamados_filtrados(
        request, status_padrao=Chamado.Status.ABERTO
    )
    visiveis = _chamados_visiveis(request.user)
    contexto = {
        # Seleção para excluir: só o Analista, e só na lista de encerrados
        "pode_excluir": (
            eh_analista(request.user) and filtros["status"] == Chamado.Status.ENCERRADO
        ),
        "chamados": chamados,
        "total": chamados.count(),
        "abertos": visiveis.filter(status=Chamado.Status.ABERTO).count(),
        "qtd_encerrados": visiveis.filter(
            status=Chamado.Status.ENCERRADO
        ).count(),
    }
    contexto.update(filtros)
    return render(request, "inventario/chamado_lista.html", contexto)


@login_required
@permission_required("inventario.add_chamado", raise_exception=True)
def chamado_novo(request):
    """Abertura do chamado na recepção.

    A hora de abertura é a hora em que este formulário é salvo — o campo
    `aberto_em` é preenchido sozinho (auto_now_add), ninguém digita.
    """
    if request.method == "POST":
        form = ChamadoAberturaForm(request.POST)
        if form.is_valid():
            chamado = form.save(commit=False)
            chamado.aberto_por = request.user
            chamado.save()
            messages.success(
                request,
                f"Chamado aberto — Ordem de Serviço {chamado.numero_os}. "
                f"Imprima a OS física (o botão está aí em cima) e entregue "
                f"ao técnico.",
            )
            return redirect("chamado_detalhe", pk=chamado.pk)
    else:
        form = ChamadoAberturaForm()
    return render(request, "inventario/chamado_form.html", {"form": form})


@login_required
@exige_analista
def chamado_excluir(request):
    """Exclui os chamados encerrados marcados na lista — só o Analista.

    Primeiro mostra a lista do que vai sumir; só apaga depois do "Sim,
    excluir". Chamado em aberto nunca entra, mesmo que o id venha no POST.
    O número das OS novas continua de onde parou (o SQLite não reaproveita
    id de linha apagada) — a menos que a exclusão apague **todos** os
    chamados e o Analista marque "recomeçar": aí a próxima OS volta a ser a
    0001. Só nesse caso, para nunca sair uma OS com o número de outra que
    ainda existe.
    """
    if request.method != "POST":
        return redirect(f"{reverse('chamado_lista')}?status=ENCERRADO")
    ids = [i for i in request.POST.getlist("chamados") if i.isdigit()]
    chamados = list(
        Chamado.objects.filter(pk__in=ids, status=Chamado.Status.ENCERRADO)
        .select_related("equipamento", "cliente", "tecnico")
        .order_by("pk")
    )
    voltar = f"{reverse('chamado_lista')}?status=ENCERRADO"
    if not chamados:
        messages.info(request, "Marque ao menos um chamado encerrado para excluir.")
        return redirect(voltar)

    apaga_todos = not Chamado.objects.exclude(
        pk__in=[c.pk for c in chamados]
    ).exists()

    if "confirmar" in request.POST:
        numeros = ", ".join(c.numero_os for c in chamados)
        recomecou = False
        with transaction.atomic():
            for chamado in chamados:
                if chamado.arquivo_os:
                    chamado.arquivo_os.delete(save=False)
                chamado.delete()
            # Confere de novo aqui dentro: alguém pode ter aberto um chamado
            # entre a tela de confirmação e o clique.
            if "recomecar" in request.POST and not Chamado.objects.exists():
                _recomeca_numeracao_das_os()
                recomecou = True
        mensagem = f"{len(chamados)} chamado(s) excluído(s): OS {numeros}."
        if recomecou:
            mensagem += " A próxima OS será a 0001."
        messages.success(request, mensagem)
        return redirect(voltar)

    return render(
        request, "inventario/chamado_excluir.html",
        {"chamados": chamados, "voltar": voltar, "apaga_todos": apaga_todos},
    )


def _recomeca_numeracao_das_os():
    """Zera o contador de id dos chamados (a OS é o id: 0001, 0002...).

    Usa o SQL que o próprio Django gera para o banco em uso — SQLite hoje,
    PostgreSQL se um dia mudar. Só pode rodar com a tabela vazia.
    """
    from django.core.management.color import no_style
    from django.db import connection

    comandos = connection.ops.sequence_reset_by_name_sql(
        no_style(), [{"table": Chamado._meta.db_table, "column": "id"}]
    )
    with connection.cursor() as cursor:
        for sql in comandos:
            cursor.execute(sql)


@login_required
def chamado_detalhe(request, pk):
    """A Ordem de Serviço: a ficha completa do chamado.

    É aqui que o técnico escreve o que fez e encerra — e o encerramento grava
    a data e a hora exatas, sem ninguém digitar.
    """
    chamado = get_object_or_404(
        Chamado.objects.select_related(
            "equipamento", "equipamento__produto", "tecnico", "cliente",
            "aberto_por", "encerrado_por",
        ),
        pk=pk,
    )
    _confere_chamado_visivel(request.user, chamado)
    pode_encerrar = request.user.has_perm("inventario.change_chamado")

    if request.method == "POST":
        if not pode_encerrar:
            raise PermissionDenied
        # Anexo avulso: a folha assinada chegou depois, com a OS já encerrada.
        if "anexar" in request.POST:
            anexo = ChamadoAnexoForm(
                request.POST, request.FILES, instance=chamado
            )
            if anexo.is_valid():
                anexo.save()
                messages.success(
                    request,
                    f"OS digitalizada anexada à Ordem de Serviço "
                    f"{chamado.numero_os}.",
                )
                return redirect("chamado_detalhe", pk=chamado.pk)
            return render(
                request, "inventario/chamado_detalhe.html",
                {
                    "chamado": chamado,
                    "form": ChamadoEncerramentoForm(instance=chamado),
                    "anexo_form": anexo,
                    "pode_encerrar": pode_encerrar,
                },
            )
        if chamado.encerrado:
            messages.info(request, "Este chamado já está encerrado.")
            return redirect("chamado_detalhe", pk=chamado.pk)
        form = ChamadoEncerramentoForm(
            request.POST, request.FILES, instance=chamado
        )
        if form.is_valid():
            chamado = form.save(commit=False)
            chamado.status = Chamado.Status.ENCERRADO
            chamado.encerrado_em = timezone.now()
            chamado.encerrado_por = request.user
            chamado.save()
            messages.success(
                request,
                f"Ordem de Serviço {chamado.numero_os} encerrada "
                f"({chamado.duracao_texto} de atendimento).",
            )
            return redirect("chamado_detalhe", pk=chamado.pk)
    else:
        form = ChamadoEncerramentoForm(instance=chamado)

    return render(
        request, "inventario/chamado_detalhe.html",
        {
            "chamado": chamado,
            "form": form,
            "anexo_form": ChamadoAnexoForm(),
            "pode_encerrar": pode_encerrar,
        },
    )


def _marca_chamados():
    """Uma "impressão digital" do estado dos chamados, em UMA consulta só.

    É o que a sentinela do painel compara de 3 em 3 segundos. Muda quando:
    entra chamado novo (`ultimo` sobe), alguém encerra (`abertos` cai e
    `ultimo_encerramento` muda). Qualquer uma dessas coisas faz a tela da
    área técnica buscar os cartões na hora, sem esperar o ciclo de 15s.

    O ponto é o custo: montar o painel inteiro são ~7 consultas mais o HTML
    de todos os cartões. Isto aqui é uma linha de agregação e uns 40 bytes de
    resposta — barato o bastante para rodar a cada 3 segundos o dia inteiro.
    """
    resumo = Chamado.objects.aggregate(
        ultimo=Max("id"),
        abertos=Count("id", filter=Q(status=Chamado.Status.ABERTO)),
        ultimo_encerramento=Max("encerrado_em"),
    )
    return "%s|%s|%s" % (
        resumo["ultimo"] or 0,
        resumo["abertos"] or 0,
        resumo["ultimo_encerramento"] or "",
    )


def _painel_dados():
    """O que o painel da área técnica mostra.

    Em cima os chamados em aberto (urgente na frente); embaixo os que foram
    encerrados hoje, para a equipe ver o que já saiu sem precisar abrir outra
    tela. `ultimo_id` é o maior número de OS já gravado — é ele que o painel
    compara a cada atualização para saber que entrou chamado novo e apitar.
    """
    base = Chamado.objects.select_related(
        "equipamento", "equipamento__produto", "tecnico", "cliente",
        "aberto_por", "encerrado_por",
    )
    limite_atraso = timezone.now() - timedelta(hours=Chamado.HORAS_ATE_ATRASO)
    abertos = (
        base.filter(status=Chamado.Status.ABERTO)
        .annotate(
            # Quem passou das 24h vai para o topo, seja qual for a urgência:
            # esperar um dia inteiro é o problema mais grave do painel.
            atraso=Case(
                When(aberto_em__lte=limite_atraso, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            # Depois: urgente na frente, normal, leve — e dentro de cada grupo
            # o mais antigo primeiro, que é quem está esperando há mais tempo.
            peso=Case(
                When(prioridade=Chamado.Prioridade.URGENTE, then=Value(1)),
                When(prioridade=Chamado.Prioridade.NORMAL, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            ),
        )
        .order_by("atraso", "peso", "aberto_em")
    )
    encerrados = (
        base.filter(
            status=Chamado.Status.ENCERRADO,
            encerrado_em__date=timezone.localdate(),
        )
        .order_by("-encerrado_em")
    )
    ultimo = Chamado.objects.order_by("-id").first()
    return {
        "chamados": abertos,
        "encerrados": encerrados,
        "total": abertos.count(),
        "urgentes": abertos.filter(
            prioridade=Chamado.Prioridade.URGENTE
        ).count(),
        "qtd_encerrados": encerrados.count(),
        "atrasados": abertos.filter(aberto_em__lte=limite_atraso).count(),
        "horas_ate_atraso": Chamado.HORAS_ATE_ATRASO,
        "ultimo_id": ultimo.pk if ultimo else 0,
        "ultimo_urgente": bool(ultimo and ultimo.urgente),
        "agora": timezone.now(),
        "segundos_atualizacao": 15,
        # De quanto em quanto tempo a sentinela pergunta "mudou alguma coisa?".
        # É este número que define em quantos segundos o chamado aberto na
        # recepção aparece na TV da área técnica.
        "segundos_sentinela": 3,
        "marca": _marca_chamados(),
    }


@login_required
def chamado_imprimir(request, pk):
    """A Ordem de Serviço em papel, do jeito que vai para a impressora.

    Sai com o **mesmo número** da OS do sistema — é por ele que a folha
    preenchida e assinada volta a ser ligada a esta ordem na hora de anexar
    a digitalização.
    """
    chamado = get_object_or_404(
        Chamado.objects.select_related(
            "equipamento", "equipamento__produto", "tecnico", "cliente",
            "aberto_por",
        ),
        pk=pk,
    )
    _confere_chamado_visivel(request.user, chamado)
    return render(
        request, "inventario/chamado_imprimir.html", {"chamado": chamado}
    )


@login_required
def chamado_arquivo(request, pk):
    """Abre a OS digitalizada anexada ao chamado.

    Passa pelo Django (e não por uma URL pública em media/) para que só quem
    está logado consiga abrir o comprovante assinado.
    """
    chamado = get_object_or_404(Chamado, pk=pk)
    _confere_chamado_visivel(request.user, chamado)
    arquivo = chamado.arquivo_os
    if not arquivo:
        raise Http404("Nenhuma OS digitalizada anexada a este chamado.")
    nome = os.path.basename(arquivo.name)
    tipos = {
        ".pdf": "application/pdf", ".png": "image/png",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    }
    tipo = tipos.get(os.path.splitext(nome)[1].lower(), "application/octet-stream")
    try:
        return FileResponse(arquivo.open("rb"), content_type=tipo, filename=nome)
    except FileNotFoundError:
        raise Http404("O arquivo não está mais na pasta media.")


@login_required
def chamado_painel(request):
    """Painel da área técnica — a tela que fica no monitor transmitindo.

    Letra grande, fundo escuro e atualização sozinha. A primeira carga vem
    montada daqui; da segunda em diante quem atualiza é o JavaScript, por
    `chamado_painel_dados`.
    """
    return render(request, "inventario/chamado_painel.html", _painel_dados())


def chamado_painel_dados(request):
    """Os cartões do painel em JSON, para a tela se atualizar sem recarregar.

    Recarregar a página inteira (o velho `<meta refresh>`) **matava o alerta
    sonoro**: o navegador só deixa tocar som depois de um clique do usuário, e
    a cada reload essa liberação era perdida. Trocando o reload por esta busca
    em segundo plano, o clique em "Ativar som" vale para o dia inteiro.

    O HTML sai do mesmo `_painel_cards.html` que a primeira carga usa — assim
    o cartão é escrito num lugar só.

    **Sem `@login_required` de propósito.** O decorator responde a sessão
    caída com um *redirect* para a tela de login — que chega no JavaScript
    como uma página HTML com status 200. O `r.json()` quebrava, o erro caía
    no `catch` e o painel congelava na TV sem avisar ninguém: a tela continua
    lá, bonita, mostrando o quadro de meia hora atrás. Respondendo **401 em
    JSON**, o painel sabe que a sessão caiu e mostra o aviso na tela.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"erro": "sessao_expirada"}, status=401)

    dados = _painel_dados()
    resposta = JsonResponse({
        "html": render_to_string(
            "inventario/_painel_cards.html", dados, request=request
        ),
        "total": dados["total"],
        "urgentes": dados["urgentes"],
        "qtd_encerrados": dados["qtd_encerrados"],
        "atrasados": dados["atrasados"],
        "ultimo_id": dados["ultimo_id"],
        "ultimo_urgente": dados["ultimo_urgente"],
        "marca": dados["marca"],
        "agora": timezone.localtime(dados["agora"]).strftime("%d/%m/%Y %H:%M:%S"),
    })
    # O painel pede sempre o estado de AGORA. Uma resposta guardada em cache
    # (pelo navegador ou por qualquer proxy no caminho) é, literalmente, o
    # chamado novo não aparecendo na tela.
    resposta["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resposta


def chamado_painel_sinal(request):
    """A sentinela: responde só "o estado é este" e nada mais.

    O painel pergunta de 3 em 3 segundos. Enquanto a resposta for igual à
    anterior, ninguém busca nada — a tela fica quieta. Na hora que a recepção
    salva um chamado, a resposta muda e o painel vai buscar os cartões na
    mesma hora, apita e pisca.

    É este endereço que faz o chamado aparecer "na hora" na área técnica sem
    pedir ao servidor que monte o painel inteiro 20 vezes por minuto.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"erro": "sessao_expirada"}, status=401)
    resposta = JsonResponse({"marca": _marca_chamados()})
    resposta["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resposta


@login_required
def chamado_historico(request):
    """Histórico por técnico, para o gerente técnico.

    Cada linha mostra a hora que o chamado foi aberto, a hora que foi
    encerrado e quanto tempo levou. Em cima, o resumo de cada técnico.
    """
    chamados, filtros = _chamados_filtrados(request)
    chamados = chamados.order_by("tecnico__username", "-aberto_em")

    # Junta os chamados por técnico e vai somando o tempo dos encerrados
    resumo = {}
    for chamado in chamados:
        nome = chamado.tecnico.get_username() if chamado.tecnico else "— sem técnico —"
        dados = resumo.setdefault(nome, {
            "total": 0, "abertos": 0, "encerrados": 0,
            "segundos": 0.0, "chamados": [],
        })
        dados["total"] += 1
        dados["chamados"].append(chamado)
        if chamado.encerrado:
            dados["encerrados"] += 1
            if chamado.duracao:
                dados["segundos"] += chamado.duracao.total_seconds()
        else:
            dados["abertos"] += 1

    linhas = []
    for nome, dados in sorted(resumo.items()):
        if dados["encerrados"]:
            total_tempo = formata_duracao(timedelta(seconds=dados["segundos"]))
            medio = formata_duracao(
                timedelta(seconds=dados["segundos"] / dados["encerrados"])
            )
        else:
            total_tempo = medio = "—"
        linhas.append({
            "nome": nome,
            "total": dados["total"],
            "abertos": dados["abertos"],
            "encerrados": dados["encerrados"],
            "tempo_total": total_tempo,
            "tempo_medio": medio,
            "chamados": dados["chamados"],
        })

    contexto = {"linhas": linhas, "total": chamados.count()}
    contexto.update(filtros)
    return render(request, "inventario/chamado_historico.html", contexto)
