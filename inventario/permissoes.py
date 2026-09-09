"""Controle de quem pode ver as áreas restritas do StockLink.

Hoje são duas áreas travadas:

* ``ver_contratos`` — a aba **Contratos** inteira;
* ``ver_pdfs``      — os PDFs anexados (contrato, aditivo e o PDF que aparece
  na ficha da máquina).

Quem manda nisso é o **owner**: o primeiro usuário cadastrado no sistema.
Ele enxerga tudo por definição e é o único que abre a tela de permissões.

Por que não usar o ``user.has_perm()`` direto? Porque o Django devolve ``True``
para qualquer superusuário, e neste sistema quase todo mundo é superusuário —
a trava não pegaria ninguém. Aqui a permissão é conferida **na marra**, olhando
o que foi realmente concedido ao usuário (direto ou por grupo). Só o owner
passa sem ter a permissão na conta.
"""

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db.models import Q

# Permissões declaradas em Contrato.Meta.permissions
VER_CONTRATOS = "ver_contratos"
VER_PDFS = "ver_pdfs"

# Usado pela tela de permissões para montar as colunas
AREAS = [
    (VER_CONTRATOS, "Aba Contratos",
     "Ver a aba Contratos, a lista e a ficha de cada contrato."),
    (VER_PDFS, "PDFs anexados",
     "Abrir os PDFs do contrato, dos aditivos e o PDF que aparece na ficha da máquina."),
]


def usuario_owner():
    """O dono do sistema: o primeiro usuário que foi cadastrado."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.order_by("id").first()


def eh_owner(user):
    if not user or not user.is_authenticated:
        return False
    owner = usuario_owner()
    return owner is not None and owner.pk == user.pk


def eh_admin(user):
    """Owner ou administrador — quem enxerga a aba Administração.

    "Administrador" aqui é o usuário marcado como **membro da equipe**
    (`is_staff`), que é a mesma marca que dá acesso ao painel `/admin/`.
    Quem tira e põe essa marca é o owner, em `/admin/` → Usuários.
    """
    if not user or not user.is_authenticated:
        return False
    return eh_owner(user) or user.is_staff


def tem_area(user, codename):
    """Diz se o usuário pode entrar na área. Owner sempre pode."""
    if not user or not user.is_authenticated:
        return False
    if eh_owner(user):
        return True
    return Permission.objects.filter(
        Q(user=user) | Q(group__user=user),
        content_type__app_label="inventario",
        codename=codename,
    ).exists()


def pode_ver_contratos(user):
    return tem_area(user, VER_CONTRATOS)


def pode_ver_pdfs(user):
    return tem_area(user, VER_PDFS)


def exige_area(codename):
    """Decorator de view: barra quem não tem a permissão da área.

    Devolve 403 em vez de mandar para o login, porque o usuário já está
    logado — ele só não tem acesso àquela parte.
    """

    def decorator(view):
        def wrapper(request, *args, **kwargs):
            if not tem_area(request.user, codename):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        wrapper.__name__ = view.__name__
        wrapper.__doc__ = view.__doc__
        return wrapper

    return decorator


def exige_admin(view):
    """Decorator de view: só o owner e os administradores passam."""

    def wrapper(request, *args, **kwargs):
        if not eh_admin(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper
