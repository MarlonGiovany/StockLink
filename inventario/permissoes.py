"""Quem pode o quê no StockLink.

Perfis
------

* **Analista** — o usuário configurado em ``settings.USUARIO_ANALISTA``
  (o ``Admin`` do Márlon). É o único que:

  - abre a tela "Usuários e permissões";
  - escolhe o perfil de cada pessoa (Técnico, Recepção, Superusuário);
  - libera as áreas restritas (aba Contratos e PDFs);
  - cria e edita usuários e grupos no ``/admin/``.

* **Superusuário** — só quem o Analista escolher. Faz tudo nas telas, mas
  não mexe em usuários nem em permissões.
* **Recepção** — o cargo da recepção: tudo no sistema, inclusive Contratos
  e PDFs, menos dar permissões.
* **Técnico** — cadastra equipamento, registra manutenção e cuida só
  das OS dele.

Recepção e Técnico são grupos (ver a migração 0018) e não precisam ser
superusuários para trabalhar.

Áreas restritas
---------------

* ``ver_contratos`` — a aba **Contratos** inteira;
* ``ver_pdfs``      — os PDFs anexados (contrato, aditivo e o PDF que aparece
  na ficha da máquina).

Por que não usar o ``user.has_perm()`` direto nas áreas? Porque o Django
devolve ``True`` para qualquer superusuário, e ser superusuário não libera
contrato: isso é o Analista quem decide, pessoa por pessoa. Aqui a permissão é
conferida **na marra**, olhando o que foi realmente concedido ao usuário
(direto ou por grupo). Só o Analista passa sem ter a permissão na conta.
"""

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.db.models import Q

# Permissões declaradas em Contrato.Meta.permissions
VER_CONTRATOS = "ver_contratos"
VER_PDFS = "ver_pdfs"

# Grupos dos perfis que não são superusuário (criados na migração 0018)
GRUPO_TECNICO = "Técnico"
GRUPO_RECEPCAO = "Recepção"

# Perfis que o Analista escolhe na tela de permissões: (código, nome, ajuda)
PERFIS = [
    ("tecnico", GRUPO_TECNICO,
     "Cadastra equipamento e registra manutenção; vê e encerra só as OS dele."),
    ("recepcao", GRUPO_RECEPCAO,
     "Tudo no sistema — clientes, fornecedores, equipamentos, chamados, "
     "contratos e PDFs, inclusive excluir —, menos dar permissões."),
    ("super", "Superusuário",
     "Faz tudo nas telas e entra no /admin/, mas não mexe em usuários e permissões."),
]

# Usado pela tela de permissões para montar as colunas
AREAS = [
    (VER_CONTRATOS, "Aba Contratos",
     "Ver a aba Contratos, a lista e a ficha de cada contrato."),
    (VER_PDFS, "PDFs anexados",
     "Abrir os PDFs do contrato, dos aditivos e o PDF que aparece na ficha da máquina."),
]


def usuario_analista():
    """O Analista: o usuário cujo login está em settings.USUARIO_ANALISTA."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(
        username=settings.USUARIO_ANALISTA
    ).first()


def eh_analista(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    return user.get_username() == settings.USUARIO_ANALISTA


def ve_todos_os_chamados(user):
    """Quem abre chamado (Recepção) e os superusuários veem todos.

    O Técnico só vê as ordens de serviço designadas a ele — na lista,
    na ficha, na impressão, no anexo e no histórico. O painel da área técnica
    não passa por aqui: ele continua mostrando todos os chamados para todos.
    """
    return bool(user and user.is_authenticated) and user.has_perm(
        "inventario.add_chamado"
    )


def perfil_do_usuario(usuario, grupos):
    """O perfil que a tela mostra marcado para o usuário (ou "" se nenhum)."""
    if usuario.is_superuser:
        return "super"
    if GRUPO_RECEPCAO in grupos:
        return "recepcao"
    if GRUPO_TECNICO in grupos:
        return "tecnico"
    return ""


def aplica_perfil(usuario, perfil):
    """Grava o perfil: superusuário ou um dos dois grupos, nunca os dois.

    Também limpa as permissões marcadas direto na conta — senão elas
    continuariam valendo por cima do perfil (um técnico com "add_cliente"
    direto seguiria cadastrando cliente). Ficam só as áreas restritas
    (Contratos e PDFs), que o Analista libera pessoa por pessoa.
    """
    extras = diretas_fora_das_areas(usuario)
    if extras:
        usuario.user_permissions.remove(*extras)
    grupos = {g.name: g for g in Group.objects.filter(
        name__in=[GRUPO_TECNICO, GRUPO_RECEPCAO]
    )}
    usuario.groups.remove(*grupos.values())
    if perfil == "tecnico" and GRUPO_TECNICO in grupos:
        usuario.groups.add(grupos[GRUPO_TECNICO])
    elif perfil == "recepcao" and GRUPO_RECEPCAO in grupos:
        usuario.groups.add(grupos[GRUPO_RECEPCAO])
    # is_staff junto: sem ele o superusuário não entra no /admin/
    super_ = perfil == "super"
    if usuario.is_superuser != super_ or usuario.is_staff != super_:
        usuario.is_superuser = usuario.is_staff = super_
        usuario.save(update_fields=["is_superuser", "is_staff"])


def diretas_fora_das_areas(usuario):
    """Permissões marcadas direto na conta que não são Contratos/PDFs."""
    return [
        p for p in usuario.user_permissions.all()
        if not (p.content_type.app_label == "inventario"
                and p.codename in (VER_CONTRATOS, VER_PDFS))
    ]


def tem_area(user, codename):
    """Diz se o usuário pode entrar na área. O Analista sempre pode."""
    if not user or not user.is_authenticated:
        return False
    if eh_analista(user):
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


def exige_analista(view):
    """Decorator de view: só o Analista passa."""

    def wrapper(request, *args, **kwargs):
        if not eh_analista(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper
