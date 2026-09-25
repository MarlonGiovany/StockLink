from django.urls import path

from . import views

urlpatterns = [
    path("", views.equipamento_lista, name="equipamento_lista"),
    path("equipamento/novo/", views.equipamento_novo, name="equipamento_novo"),
    path("produtos/novo/", views.produto_novo, name="produto_novo"),
    path("equipamento/<int:pk>/", views.equipamento_detalhe, name="equipamento_detalhe"),
    path("equipamento/<int:pk>/editar/", views.equipamento_editar, name="equipamento_editar"),
    path("equipamento/<int:pk>/excluir/", views.equipamento_excluir, name="equipamento_excluir"),
    path("equipamento/<int:pk>/manutencao/", views.manutencao_nova, name="manutencao_nova"),
    path("equipamento/<int:pk>/locacao/", views.locacao_nova, name="locacao_nova"),
    path("locacao/<int:pk>/encerrar/", views.locacao_encerrar, name="locacao_encerrar"),
    path("locacao/<int:pk>/contrato/", views.locacao_vincular_contrato,
         name="locacao_vincular_contrato"),

    path("fornecedores/", views.fornecedor_lista, name="fornecedor_lista"),
    path("fornecedores/novo/", views.fornecedor_novo, name="fornecedor_novo"),
    path("clientes/", views.cliente_lista, name="cliente_lista"),
    path("clientes/novo/", views.cliente_novo, name="cliente_novo"),

    path("contratos/", views.contrato_lista, name="contrato_lista"),
    path("contratos/novo/", views.contrato_novo, name="contrato_novo"),
    path("contratos/<int:pk>/", views.contrato_detalhe, name="contrato_detalhe"),
    path("contratos/<int:pk>/editar/", views.contrato_editar, name="contrato_editar"),
    path("contratos/<int:pk>/excluir/", views.contrato_excluir, name="contrato_excluir"),
    path("contratos/<int:pk>/aditivo/", views.aditivo_novo, name="aditivo_novo"),
    path("contratos/<int:pk>/valor-em-lote/", views.locacao_valor_em_lote,
         name="locacao_valor_em_lote"),
    path("aditivo/<int:pk>/editar/", views.aditivo_editar, name="aditivo_editar"),
    path("aditivo/<int:pk>/excluir/", views.aditivo_excluir, name="aditivo_excluir"),

    # PDFs passam pelo Django para a permissão valer (não são mais URL pública)
    path("contratos/<int:pk>/pdf/", views.contrato_pdf, name="contrato_pdf"),
    path("aditivo/<int:pk>/pdf/", views.aditivo_pdf, name="aditivo_pdf"),

    path("permissoes/", views.permissoes_usuarios, name="permissoes_usuarios"),

    # Chamados / Ordem de Serviço
    path("chamados/", views.chamado_lista, name="chamado_lista"),
    path("chamados/novo/", views.chamado_novo, name="chamado_novo"),
    path("chamados/painel/", views.chamado_painel, name="chamado_painel"),
    path("chamados/painel/dados/", views.chamado_painel_dados,
         name="chamado_painel_dados"),
    # Sentinela: consulta barata, de 3 em 3s, que avisa o painel quando entrou
    # ou saiu chamado — é o que faz a OS aparecer na hora na área técnica.
    path("chamados/painel/sinal/", views.chamado_painel_sinal,
         name="chamado_painel_sinal"),
    path("chamados/historico/", views.chamado_historico, name="chamado_historico"),
    path("chamados/<int:pk>/", views.chamado_detalhe, name="chamado_detalhe"),
    path("chamados/<int:pk>/imprimir/", views.chamado_imprimir,
         name="chamado_imprimir"),
    path("chamados/<int:pk>/arquivo/", views.chamado_arquivo,
         name="chamado_arquivo"),
]
