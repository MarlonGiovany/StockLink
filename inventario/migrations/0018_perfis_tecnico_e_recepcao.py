"""Cria os grupos dos perfis que não são superusuário.

* **Técnico** — cadastra equipamento e registra manutenção; vê e
  encerra só as ordens de serviço designadas a ele. Não cadastra cliente nem
  fornecedor e não exclui nada.
* **Recepção** — todas as permissões do sistema: cadastra e exclui
  clientes, fornecedores e equipamentos, abre chamado e vê todas as OS
  (`ve_todos_os_chamados`), e enxerga Contratos e PDFs. Só não mexe em
  usuários nem em permissões — isso é do Analista, e não é permissão de
  grupo.

O antigo grupo "Operador" vira o "Técnico" (quem estava nele continua
nele), já com as permissões novas.

O Analista pode ajustar as permissões de cada grupo depois, em /admin/ →
Grupos. Rodar a migração de novo não desfaz o ajuste: ela só roda uma vez.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

TECNICO = [
    "view_equipamento", "add_equipamento",
    "view_produto", "add_produto",
    "view_manutencao", "add_manutencao",
    "view_cliente", "view_fornecedor",
    "view_locacao", "view_movimentacao",
    "view_chamado", "change_chamado",
]
# Recepção: todas as permissões do app inventario (None = todas)
RECEPCAO = None


def cria_grupos(apps, schema_editor):
    # Num banco novo as permissões só nascem depois de todas as migrações;
    # cria agora para poder colocá-las nos grupos.
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    operador = Group.objects.filter(name="Operador").first()
    if operador and not Group.objects.filter(name="Técnico").exists():
        operador.name = "Técnico"
        operador.save()

    for nome, codenames in (("Técnico", TECNICO), ("Recepção", RECEPCAO)):
        grupo, _ = Group.objects.get_or_create(name=nome)
        permissoes = Permission.objects.filter(content_type__app_label="inventario")
        if codenames is not None:
            permissoes = permissoes.filter(codename__in=codenames)
        grupo.permissions.set(permissoes)


def desfaz(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Recepção").delete()
    Group.objects.filter(name="Técnico").update(name="Operador")


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("inventario", "0017_alter_aditivo_valor_alter_contrato_valor_and_more"),
    ]

    operations = [migrations.RunPython(cria_grupos, desfaz)]
