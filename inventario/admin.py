from django.contrib import admin

from .models import (
    Aditivo,
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


class ManutencaoInline(admin.TabularInline):
    model = Manutencao
    extra = 0


class LocacaoInline(admin.TabularInline):
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


@admin.register(Equipamento)
class EquipamentoAdmin(admin.ModelAdmin):
    list_display = (
        "numero_patrimonio", "produto", "marca", "modelo", "numero_serie",
        "local", "status",
    )
    list_filter = ("produto", "status", "marca", "fornecedor")
    search_fields = (
        "marca", "modelo", "numero_serie", "numero_patrimonio", "local",
        "produto__nome",
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
class LocacaoAdmin(admin.ModelAdmin):
    list_display = ("equipamento", "cliente", "contrato", "valor", "data_inicio", "data_fim", "ativa")
    list_filter = ("ativa",)
    search_fields = ("equipamento__numero_patrimonio", "cliente__nome", "contrato__numero")


@admin.register(Manutencao)
class ManutencaoAdmin(admin.ModelAdmin):
    list_display = ("equipamento", "data", "tecnico", "custo")
    search_fields = ("equipamento__numero_patrimonio", "tecnico")


class AditivoInline(admin.TabularInline):
    model = Aditivo
    extra = 0
    fields = ("numero", "tipo", "descricao", "valor", "data", "arquivo")


@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    list_display = ("numero", "titulo", "cliente", "data_contrato", "valor", "arquivo")
    list_filter = ("data_contrato", "cliente")
    search_fields = ("numero", "titulo", "cliente__nome")
    date_hierarchy = "data_contrato"
    readonly_fields = ("criado_em", "criado_por")
    inlines = [AditivoInline]


@admin.register(Aditivo)
class AditivoAdmin(admin.ModelAdmin):
    list_display = ("contrato", "numero", "tipo", "descricao", "valor", "data")
    list_filter = ("tipo", "data")
    search_fields = ("contrato__numero", "descricao")
    readonly_fields = ("criado_em", "criado_por")


@admin.register(Movimentacao)
class MovimentacaoAdmin(admin.ModelAdmin):
    list_display = ("data", "tipo", "equipamento", "descricao", "usuario")
    list_filter = ("tipo",)
    search_fields = ("equipamento__numero_patrimonio", "descricao")
    readonly_fields = ("equipamento", "tipo", "descricao", "usuario", "data")
