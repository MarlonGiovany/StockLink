"""Passa todo mundo (menos o Analista) para os perfis novos — uma vez só.

Tira o superusuário de todos, menos do Analista e de quem vier em
--superusuario, e coloca os demais no grupo "Usuário comum" — ou em
"Recepção", para quem vier em --recepcao ou já estiver nesse grupo. Quem vier
em --contratos ganha a aba Contratos e os PDFs. Depois disso, quem decide
perfil é o Analista, na tela "Usuários e permissões".

Uso:
    python manage.py aplicar_perfis --recepcao Pedrorios1              # só mostra
    python manage.py aplicar_perfis --recepcao Pedrorios1 --confirmar  # aplica

Sem --confirmar nada é gravado: o comando só lista o que faria.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventario.permissoes import (
    GRUPO_COMUM,
    GRUPO_RECEPCAO,
    PERFIS,
    VER_CONTRATOS,
    VER_PDFS,
    aplica_perfil,
    perfil_do_usuario,
)

NOMES = {"": "— sem perfil —", **{codigo: nome for codigo, nome, _ in PERFIS}}


class Command(BaseCommand):
    help = "Tira o superusuário de todos menos o Analista e aplica os perfis."

    def add_arguments(self, parser):
        parser.add_argument(
            "--recepcao", nargs="*", default=[], metavar="LOGIN",
            help="Logins que ficam no perfil Recepção.",
        )
        parser.add_argument(
            "--superusuario", nargs="*", default=[], metavar="LOGIN",
            help="Logins que ficam como Superusuário.",
        )
        parser.add_argument(
            "--contratos", nargs="*", default=[], metavar="LOGIN",
            help="Logins que ganham a aba Contratos e os PDFs.",
        )
        parser.add_argument(
            "--confirmar", action="store_true",
            help="Grava as mudanças. Sem isto, só mostra o que faria.",
        )

    def handle(self, *args, recepcao, superusuario, contratos, confirmar, **options):
        User = get_user_model()
        analista = User.objects.filter(username=settings.USUARIO_ANALISTA).first()
        if not analista or not analista.is_active:
            raise CommandError(
                f"O Analista ({settings.USUARIO_ANALISTA!r}) não existe ou está "
                f"inativo — sem ele ninguém conseguiria dar permissões. Nada foi "
                f"alterado."
            )
        if not Group.objects.filter(name__in=[GRUPO_COMUM, GRUPO_RECEPCAO]).count() == 2:
            raise CommandError("Rode as migrações antes (python manage.py migrate).")
        citados = set(recepcao) | set(superusuario) | set(contratos)
        faltando = citados - set(
            User.objects.filter(username__in=citados).values_list("username", flat=True)
        )
        if faltando:
            raise CommandError(f"Login não encontrado: {', '.join(sorted(faltando))}.")

        self.stdout.write(
            f"Analista: {analista.username} (continua superusuário, com tudo)\n"
        )
        areas = list(Permission.objects.filter(
            content_type__app_label="inventario",
            codename__in=[VER_CONTRATOS, VER_PDFS],
        ))
        mudancas = []
        for usuario in User.objects.exclude(pk=analista.pk).order_by("username"):
            grupos = {g.name for g in usuario.groups.all()}
            atual = perfil_do_usuario(usuario, grupos)
            if usuario.username in superusuario:
                novo = "super"
            elif usuario.username in recepcao or GRUPO_RECEPCAO in grupos:
                novo = "recepcao"
            else:
                novo = "comum"
            libera = usuario.username in contratos and not all(
                a in usuario.user_permissions.all() for a in areas
            )
            marca = "" if usuario.is_active else "  (inativo)"
            if libera:
                marca += "  + contratos e PDFs"
            # is_staff sobrando (o antigo "administrador") também sai
            muda = atual != novo or (usuario.is_staff and novo != "super") or libera
            seta = "" if muda else "  (sem mudança)"
            self.stdout.write(
                f"  {usuario.username:<20} {NOMES[atual]:<16} -> {NOMES[novo]}{seta}{marca}"
            )
            if muda:
                mudancas.append((usuario, novo, libera))

        if not confirmar:
            self.stdout.write(self.style.WARNING(
                f"\n{len(mudancas)} usuário(s) mudariam. Nada foi gravado — "
                f"rode de novo com --confirmar para aplicar."
            ))
            return

        with transaction.atomic():
            if not (analista.is_superuser and analista.is_staff):
                analista.is_superuser = analista.is_staff = True
                analista.save(update_fields=["is_superuser", "is_staff"])
            for usuario, novo, libera in mudancas:
                aplica_perfil(usuario, novo)
                if libera:
                    usuario.user_permissions.add(*areas)
        self.stdout.write(self.style.SUCCESS(
            f"\n{len(mudancas)} usuário(s) atualizados."
        ))
