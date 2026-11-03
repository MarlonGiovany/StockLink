"""Deixa as travas de acesso disponíveis em qualquer template.

Sem isso, cada template teria que receber os mesmos três valores da view.
O menu do topo (base.html) precisa deles em toda página.
"""

from datetime import date

from django.conf import settings

from .permissoes import eh_analista, pode_ver_contratos, pode_ver_pdfs


def identidade(request):
    """O nome da empresa, para as telas e para a OS impressa.

    Vem do settings.py e passa por aqui para que nenhum template precise
    escrever o nome na mão — eram 27 lugares antes disto.
    """
    return {
        "nome_sistema": settings.NOME_SISTEMA,
        "nome_empresa": settings.NOME_EMPRESA,
        "tema_natal": tema_natal_ligado(),
    }


def tema_natal_ligado(hoje=None):
    """O tema de Natal está ligado? 'auto' vale de 1º/dez a 6/jan."""
    modo = settings.TEMA_NATAL
    if modo == "sim":
        return True
    if modo != "auto":
        return False
    hoje = hoje or date.today()
    return hoje.month == 12 or (hoje.month == 1 and hoje.day <= 6)


def permissoes(request):
    user = getattr(request, "user", None)
    return {
        "eh_analista": eh_analista(user),
        "pode_ver_contratos": pode_ver_contratos(user),
        "pode_ver_pdfs": pode_ver_pdfs(user),
    }
