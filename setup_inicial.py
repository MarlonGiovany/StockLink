import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_DEBUG", "True")  # roda no console, não é o site no ar
django.setup()

from getpass import getpass

from django.conf import settings
from django.contrib.auth.models import User, Group

# Superusuario admin
if not User.objects.filter(username=settings.USUARIO_ANALISTA).exists():
    admin_email = os.environ.get("ADMIN_EMAIL") or input("E-mail do admin: ")
    admin_senha = os.environ.get("ADMIN_SENHA") or getpass("Senha do admin: ")
    User.objects.create_superuser(settings.USUARIO_ANALISTA, admin_email, admin_senha)
    print(f"Superusuario '{settings.USUARIO_ANALISTA}' (Analista) criado")
else:
    print(f"Superusuario '{settings.USUARIO_ANALISTA}' (Analista) ja existe")

# Grupos dos perfis ("Técnico" e "Recepção") vêm da migração 0018.
# O superusuário acima é o Analista (settings.USUARIO_ANALISTA).
grupo = Group.objects.get(name="Técnico")

# Técnico de exemplo
if not User.objects.filter(username="operador").exists():
    operador_senha = os.environ.get("OPERADOR_SENHA") or getpass("Senha do operador: ")
    u = User.objects.create_user("operador", password=operador_senha)
    u.groups.add(grupo)
    print("Usuario 'operador' criado")
else:
    print("Usuario 'operador' ja existe")
