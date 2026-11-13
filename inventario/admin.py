from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AdminFileWidget
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from django.db import models

from .acesso import AdminLoginForm
from .forms import (
    LinkProtegidoMixin, confere_status_de_maquina_locada, protege_arquivo,
)
from .permissoes import eh_analista, pode_ver_contratos
from .models import (
    Aditivo,
    Chamado,
    Cliente,
    Contrato,
    Equipamento,
    Fornecedor,
    Locacao,
    Manutencao,
    Movimentacao,
    Produto,
)

# Marca do painel administrativo (substitui "Administração do Django")
admin.site.site_header = "StockLink — Administração"
admin.site.site_title = "StockLink"
admin.site.index_title = "Painel de administração"

# O login do /admin/ tem o mesmo limite de senhas erradas da tela do sistema
admin.site.login_form = AdminLoginForm


# Usuários e grupos: só o Analista vê e mexe. Um superusuário que não é o Analista entra no
# /admin/ para cuidar dos dados, mas não consegue se dar (nem dar a ninguém)
# permissão, perfil ou superusuário — isso é do Analista.
class SoAnalistaMixin:
    def has_module_permission(self, request):
        return eh_analista(request.user)

    def has_view_permission(self, request, obj=None):
        return eh_analista(request.user)

    def has_add_permission(self, request):
        return eh_analista(request.user)

    def has_change_permission(self, request, obj=None):
        return eh_analista(request.user)

    def has_delete_permission(self, request, obj=None):
        return eh_analista(request.user)


class UsuarioAdmin(SoAnalistaMixin, UserAdmin):
    pass


class GrupoAdmin(SoAnalistaMixin, GroupAdmin):
    pass


# Contratos e aditivos: a mesma trava da aba Contratos do sistema. Sem isto, um
# superusuário que não recebeu a área "ver_contratos" levava 403 em /contratos/
# mas abria a lista inteira em /admin/ — o Django libera tudo para superusuário.
class SoComAreaContratosMixin:
    def has_module_permission(self, request):
        return pode_ver_contratos(request.user) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return pode_ver_contratos(request.user) and super().has_view_permission(request, obj)

    def has_add_permission(self, request, *args):
        return pode_ver_contratos(request.user) and super().has_add_permission(request, *args)

    def has_change_permission(self, request, obj=None):
        return pode_ver_contratos(request.user) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return pode_ver_contratos(request.user) and super().has_delete_permission(request, obj)


admin.site.unregister(get_user_model())
admin.site.unregister(Group)
admin.site.register(get_user_model(), UsuarioAdmin)
admin.site.register(Group, GrupoAdmin)


# PDFs e OS digitalizadas: o "Atualmente: arquivo" do admin abre pela view que
# confere a permissão, igual às telas do sistema (ver LinkProtegidoMixin).
class ArquivoProtegidoAdminInput(LinkProtegidoMixin, AdminFileWidget):
    pass


def form_com_arquivo_protegido(campo, rota):
    class Form(forms.ModelForm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            protege_arquivo(self, campo, rota)

    return Form


ARQUIVO_PROTEGIDO = {models.FileField: {"widget": ArquivoProtegidoAdminInput}}


class ManutencaoInline(admin.TabularInline):
    model = Manutencao
    extra = 0


# Contrato e aditivo da locação: quem não tem a área Contratos não vê de qual
# contrato cada locação é (o aditivo aparece como "Aditivo 1 — <contrato>").
# Fora do formulário, o vínculo que já existe fica intacto ao salvar.
CAMPOS_DE_CONTRATO_DA_LOCACAO = ("contrato", "aditivo")


class EscondeContratoDaLocacaoMixin:
    def get_exclude(self, request, obj=None):
        excluidos = list(super().get_exclude(request, obj) or [])
        if not pode_ver_contratos(request.user):
            excluidos += CAMPOS_DE_CONTRATO_DA_LOCACAO
        return excluidos or None


class LocacaoInline(EscondeContratoDaLocacaoMixin, admin.TabularInline):
    model = Locacao
    extra = 0


class MovimentacaoInline(admin.TabularInline):
    model = Movimentacao
    extra = 0
    readonly_fields = ("tipo", "descricao", "usuario", "data")
    can_delete = False


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("nome", "quantidade", "pede_configuracao", "ordem", "ativo")
    list_editable = ("pede_configuracao", "ordem", "ativo")
    search_fields = ("nome",)

    @admin.display(description="Equipamentos")
    def quantidade(self, obj):
        return obj.equipamentos.count()


class EquipamentoAdminForm(forms.ModelForm):
    """Mesma trava da tela do sistema: máquina locada não vira Disponível."""

    def clean(self):
        dados = super().clean()
        confere_status_de_maquina_locada(self, dados)
        return dados


@admin.register(Equipamento)
class EquipamentoAdmin(admin.ModelAdmin):
    form = EquipamentoAdminForm
    list_display = (
        "numero_patrimonio", "produto", "marca", "modelo", "numero_serie",
        "local", "setor", "status",
    )
    list_filter = ("produto", "status", "marca", "fornecedor")
    search_fields = (
        "marca", "modelo", "numero_serie", "numero_patrimonio", "local",
        "setor", "produto__nome",
    )
    inlines = [ManutencaoInline, LocacaoInline, MovimentacaoInline]


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ("nome", "cnpj", "telefone", "email")
    search_fields = ("nome", "cnpj")


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "documento", "telefone", "email")
    search_fields = ("nome", "documento")


@admin.register(Locacao)
class LocacaoAdmin(EscondeContratoDaLocacaoMixin, admin.ModelAdmin):
    list_display = ("equipamento", "cliente", "contrato", "valor", "data_inicio", "data_fim", "ativa")
    list_filter = ("ativa",)
    search_fields = ("equipamento__numero_patrimonio", "cliente__nome")

    def get_list_display(self, request):
        colunas = super().get_list_display(request)
        if pode_ver_contratos(request.user):
            return colunas
        return [c for c in colunas if c not in CAMPOS_DE_CONTRATO_DA_LOCACAO]

    def get_search_fields(self, request):
        # Buscar pelo número do contrato também revelaria o contrato
        if pode_ver_contratos(request.user):
            return self.search_fields + ("contrato__numero",)
        return self.search_fields


@admin.register(Manutencao)
class ManutencaoAdmin(admin.ModelAdmin):
    list_display = ("equipamento", "data", "tecnico", "custo")
    search_fields = ("equipamento__numero_patrimonio", "tecnico")


class AditivoInline(SoComAreaContratosMixin, admin.TabularInline):
    model = Aditivo
    extra = 0
    fields = ("numero", "tipo", "descricao", "valor", "data", "arquivo")
    form = form_com_arquivo_protegido("arquivo", "aditivo_pdf")
    formfield_overrides = ARQUIVO_PROTEGIDO


@admin.register(Contrato)
class ContratoAdmin(SoComAreaContratosMixin, admin.ModelAdmin):
    list_display = ("__str__", "titulo", "cliente", "data_contrato", "valor", "arquivo")
    list_filter = ("data_contrato", "cliente")
    search_fields = ("titulo", "cliente__nome")
    date_hierarchy = "data_contrato"
    readonly_fields = ("criado_em", "criado_por")
    inlines = [AditivoInline]
    form = form_com_arquivo_protegido("arquivo", "contrato_pdf")
    formfield_overrides = ARQUIVO_PROTEGIDO


@admin.register(Aditivo)
class AditivoAdmin(SoComAreaContratosMixin, admin.ModelAdmin):
    list_display = ("contrato", "numero", "tipo", "descricao", "valor", "data")
    list_filter = ("tipo", "data")
    search_fields = ("contrato__cliente__nome", "descricao")
    readonly_fields = ("criado_em", "criado_por")
    form = form_com_arquivo_protegido("arquivo", "aditivo_pdf")
    formfield_overrides = ARQUIVO_PROTEGIDO


@admin.register(Movimentacao)
class MovimentacaoAdmin(admin.ModelAdmin):
    list_display = ("data", "tipo", "equipamento", "descricao", "usuario")
    list_filter = ("tipo",)
    search_fields = ("equipamento__numero_patrimonio", "descricao")
    readonly_fields = ("equipamento", "tipo", "descricao", "usuario", "data")


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    list_display = (
        "id", "aberto_em", "prioridade", "cliente", "equipamento", "tecnico",
        "status", "encerrado_em", "duracao_texto",
    )
    list_filter = ("prioridade", "status", "tecnico", "cliente")
    search_fields = (
        "equipamento__numero_patrimonio", "descricao", "realizado",
        "tecnico__username", "solicitante", "cliente__nome",
    )
    date_hierarchy = "aberto_em"
    # As duas pontas do tempo são gravadas pelo sistema — ninguém digita
    readonly_fields = ("aberto_em", "aberto_por", "encerrado_em", "encerrado_por")
    form = form_com_arquivo_protegido("arquivo_os", "chamado_arquivo")
    formfield_overrides = ARQUIVO_PROTEGIDO

    @admin.display(description="Tempo")
    def duracao_texto(self, obj):
        return obj.duracao_texto
