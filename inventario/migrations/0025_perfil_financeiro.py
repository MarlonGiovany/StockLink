"""Cria o grupo do perfil **Financeiro**.

Contratos e aditivos (ver, anexar, editar, cancelar — sem excluir), PDFs e
Dashboard Gerencial já no perfil; clientes e fornecedores (cadastra e edita,
sem excluir); equipamentos só para consulta. Nenhuma permissão de chamado:
o Financeiro não vê nem abre chamados.

O Analista pode ajustar depois em /admin/ → Grupos; esta migração só roda
uma vez.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

FINANCEIRO = [
    # Equipamentos: só consulta (inclui o histórico da ficha)
    "view_equipamento", "view_produto", "view_locacao",
    "view_movimentacao", "view_manutencao",
    # Contratos e aditivos: tudo, menos excluir
    "view_contrato", "add_contrato", "change_contrato",
    "view_aditivo", "add_aditivo", "change_aditivo",
    # Clientes e fornecedores: cadastra e edita, sem excluir
    "view_cliente", "add_cliente", "change_cliente",
    "view_fornecedor", "add_fornecedor", "change_fornecedor",
    # Áreas restritas, já liberadas pelo perfil
    "ver_contratos", "ver_pdfs", "ver_dashboard",
]


def cria_grupo(apps, schema_editor):
    # Num banco novo as permissões só nascem depois de todas as migrações;
    # cria agora para poder colocá-las no grupo.
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    grupo, _ = Group.objects.get_or_create(name="Financeiro")
    grupo.permissions.set(Permission.objects.filter(
        content_type__app_label="inventario", codename__in=FINANCEIRO,
    ))


def desfaz(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name="Financeiro").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("inventario", "0024_dashboard_e_valor_mensal"),
    ]

    operations = [migrations.RunPython(cria_grupo, desfaz)]
