import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_DEBUG", "True")  # roda no console, não é o site no ar
django.setup()

from getpass import getpass

from django.contrib.auth.models import User, Group, Permission

# Superusuario admin
if not User.objects.filter(username="admin").exists():
    admin_email = os.environ.get("ADMIN_EMAIL") or input("E-mail do admin: ")
    admin_senha = os.environ.get("ADMIN_SENHA") or getpass("Senha do admin: ")
    User.objects.create_superuser("admin", admin_email, admin_senha)
    print("Superusuario 'admin' criado")
else:
    print("Superusuario 'admin' ja existe")

# Grupo Operador: pode ver, cadastrar e registrar manutencao/locacao, mas NAO excluir
grupo, _ = Group.objects.get_or_create(name="Operador")
codenames = [
    "add_equipamento", "change_equipamento", "view_equipamento",
    "add_produto", "view_produto",
    "add_manutencao", "view_manutencao",
    "add_locacao", "change_locacao", "view_locacao",
    "add_cliente", "view_cliente",
    "add_fornecedor", "view_fornecedor",
    "add_contrato", "change_contrato", "view_contrato",
    "add_aditivo", "change_aditivo", "view_aditivo",
    "view_movimentacao",
]
perms = Permission.objects.filter(codename__in=codenames, content_type__app_label="inventario")
grupo.permissions.set(perms)
print(f"Grupo 'Operador' configurado com {perms.count()} permissoes")

# Usuario comum de exemplo
if not User.objects.filter(username="operador").exists():
    operador_senha = os.environ.get("OPERADOR_SENHA") or getpass("Senha do operador: ")
    u = User.objects.create_user("operador", password=operador_senha)
    u.groups.add(grupo)
    print("Usuario 'operador' criado")
else:
    print("Usuario 'operador' ja existe")
