"""Limite de tentativas de login.

Quem erra a senha 5 vezes em 15 minutos, com o mesmo usuário e do mesmo IP,
fica sem conseguir entrar até os erros mais antigos saírem da janela de 15
minutos — nem com a senha certa. É o que impede alguém na internet de ficar
testando senhas no usuário Admin sem parar.

A trava é por usuário + IP: quem tenta de fora não consegue trancar a
recepção, que entra de outro endereço.
"""

from datetime import timedelta

from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from .models import TentativaDeLogin

LIMITE_DE_ERROS = 5
MINUTOS_DE_BLOQUEIO = 15

MENSAGEM_BLOQUEIO = (
    f"Muitas tentativas com senha errada. Por segurança, o login deste "
    f"usuário está bloqueado por até {MINUTOS_DE_BLOQUEIO} minutos. "
    f"Aguarde e tente de novo."
)


def ip_do_pedido(request):
    """O IP de quem está tentando entrar.

    No PythonAnywhere o pedido chega pelo proxy deles, que põe o IP
    verdadeiro no cabeçalho X-Real-IP; sem proxy (no computador de
    desenvolvimento) vale o REMOTE_ADDR.
    """
    if request is None:
        return ""
    meta = request.META
    return (meta.get("HTTP_X_REAL_IP") or meta.get("REMOTE_ADDR") or "")[:45]


def _chave_usuario(usuario):
    # "admin" e "ADMIN" contam como o mesmo usuário: quem testa senhas não
    # ganha tentativas extras trocando maiúsculas.
    return (usuario or "").strip().casefold()[:150]


def _inicio_da_janela():
    return timezone.now() - timedelta(minutes=MINUTOS_DE_BLOQUEIO)


def esta_bloqueado(usuario, ip):
    return TentativaDeLogin.objects.filter(
        usuario=_chave_usuario(usuario), ip=ip, quando__gte=_inicio_da_janela()
    ).count() >= LIMITE_DE_ERROS


def registra_erro(usuario, ip):
    # Aproveita para jogar fora o que já saiu da janela: a tabela não cresce.
    TentativaDeLogin.objects.filter(quando__lt=_inicio_da_janela()).delete()
    TentativaDeLogin.objects.create(usuario=_chave_usuario(usuario), ip=ip)


def limpa_erros(usuario, ip):
    TentativaDeLogin.objects.filter(usuario=_chave_usuario(usuario), ip=ip).delete()


class LimiteDeTentativasMixin:
    """Põe o limite de tentativas num formulário de login do Django."""

    bloqueado = False

    def clean(self):
        usuario = self.cleaned_data.get("username")
        ip = ip_do_pedido(self.request)
        if usuario and esta_bloqueado(usuario, ip):
            # Nem confere a senha: senão quem testa senhas descobriria a
            # certa mesmo com o login fechado.
            self.bloqueado = True
            raise forms.ValidationError(MENSAGEM_BLOQUEIO, code="bloqueado")
        try:
            dados = super().clean()
        except forms.ValidationError:
            if usuario and self.cleaned_data.get("password"):
                registra_erro(usuario, ip)
            raise
        if usuario:
            limpa_erros(usuario, ip)
        return dados


class LoginForm(LimiteDeTentativasMixin, AuthenticationForm):
    pass


class AdminLoginForm(LimiteDeTentativasMixin, AdminAuthenticationForm):
    pass
