"""Passe de acesso ao Sistema de Tarefas (o "login automático").

Quem tem a área **Sistema de Tarefas** liberada vê a aba *Tarefas* no menu.
Ao clicar, o StockLink gera um passe curto e manda a pessoa para o Sistema de
Tarefas, que confere o passe e abre o painel já no perfil ligado a este
usuário — sem pedir senha.

Como o passe é feito
--------------------

É um JWT HS256 escrito à mão com a biblioteca padrão do Python (``hmac`` +
``hashlib``), para não acrescentar dependência ao projeto:

* ``iss`` = ``stocklink`` e ``aud`` = ``inforlink-tarefas`` — quem emite e
  para quem serve;
* ``sub`` = o login do usuário no StockLink (o Sistema de Tarefas procura o
  perfil que tem esse login cadastrado em *Equipe*);
* ``iat`` / ``exp`` — vale 60 segundos;
* ``jti`` — número aleatório; o Sistema de Tarefas guarda os já usados, então
  cada passe só funciona uma vez.

A assinatura usa ``TAREFAS_SSO_SECRET``, uma chave que só este servidor e o
do Sistema de Tarefas conhecem (variável de ambiente, nunca no repositório).
Sem a chave, ninguém fabrica um passe válido; com a chave errada, o Sistema de
Tarefas recusa.

O passe viaja depois do ``#`` no endereço (o "fragmento"): o navegador não o
envia a nenhum servidor nem o grava nos registros de acesso.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from django.conf import settings

VALIDADE_SEGUNDOS = 60
EMISSOR = "stocklink"
DESTINO = "inforlink-tarefas"
TAMANHO_MINIMO_DA_CHAVE = 32


def configurado():
    """A chave existe e tem um tamanho que não dá para adivinhar?"""
    return len(settings.TAREFAS_SSO_SECRET or "") >= TAMANHO_MINIMO_DA_CHAVE


def _b64(dados):
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def _json(objeto):
    return json.dumps(objeto, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def gera_passe(username, agora=None):
    """O passe assinado para ``username``, ou ``None`` se falta a chave."""
    if not configurado():
        return None
    agora = int(time.time() if agora is None else agora)
    corpo = {
        "iss": EMISSOR,
        "aud": DESTINO,
        "sub": username,
        "iat": agora,
        "exp": agora + VALIDADE_SEGUNDOS,
        "jti": secrets.token_urlsafe(24),
    }
    assinado = _b64(_json({"alg": "HS256", "typ": "JWT"})) + "." + _b64(_json(corpo))
    assinatura = hmac.new(
        settings.TAREFAS_SSO_SECRET.encode("utf-8"),
        assinado.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return assinado + "." + _b64(assinatura)


def endereco_de_entrada(passe):
    """Para onde o navegador vai: a tela /sso do Sistema de Tarefas."""
    return settings.TAREFAS_URL.rstrip("/") + "/sso#passe=" + passe
