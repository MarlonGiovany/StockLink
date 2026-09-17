"""Deixa as travas de acesso disponíveis em qualquer template.

Sem isso, cada template teria que receber os mesmos três valores da view.
O menu do topo (base.html) precisa deles em toda página.
"""

from django.conf import settings

from .permissoes import eh_admin, eh_owner, pode_ver_contratos, pode_ver_pdfs


def identidade(request):
    """O nome da empresa, para as telas e para a OS impressa.

    Vem do settings.py e passa por aqui para que nenhum template precise
    escrever o nome na mão — eram 27 lugares antes disto.
    """
    return {
        "nome_sistema": settings.NOME_SISTEMA,
        "nome_empresa": settings.NOME_EMPRESA,
    }


def permissoes(request):
    user = getattr(request, "user", None)
    return {
        "eh_owner": eh_owner(user),
        "eh_admin": eh_admin(user),
        "pode_ver_contratos": pode_ver_contratos(user),
        "pode_ver_pdfs": pode_ver_pdfs(user),
    }
