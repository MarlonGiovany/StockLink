"""Aviso por e-mail ao técnico quando um chamado é vinculado a ele.

Dispara na abertura do chamado e sempre que o técnico for trocado na
edição — nunca quando só outro campo muda (ver `chamado_novo` e
`chamado_editar` em `views.py`).

Sem EMAIL_HOST_USER configurado (ver `config/settings.py`) ou sem o e-mail
do próprio técnico cadastrado, o aviso é só pulado — nunca impede salvar o
chamado. Uma falha do servidor de e-mail (fora do ar, credencial errada)
também não impede o salvamento: fica registrada no log para o Analista
investigar.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def configurado():
    """Existe uma conta de envio configurada?"""
    return bool(settings.EMAIL_HOST_USER)


def avisa_tecnico(chamado):
    """Manda ao técnico designado um e-mail com os dados da OS."""
    if not configurado():
        return
    tecnico = chamado.tecnico
    if not tecnico or not tecnico.email:
        return

    assunto = f"OS {chamado.numero_os} designada para você — {settings.NOME_SISTEMA}"
    corpo = (
        f"Olá, {tecnico.get_full_name() or tecnico.get_username()}.\n\n"
        f"A Ordem de Serviço {chamado.numero_os} foi designada para você.\n\n"
        f"Cliente: {chamado.cliente or '— não informado —'}\n"
        f"Máquina: INF-{chamado.equipamento.numero_patrimonio} "
        f"{chamado.equipamento.marca} {chamado.equipamento.modelo}\n"
        f"Urgência: {chamado.get_prioridade_display()}\n\n"
        f"O que fazer:\n{chamado.descricao}\n"
    )
    try:
        send_mail(assunto, corpo, settings.DEFAULT_FROM_EMAIL, [tecnico.email])
    except Exception:
        logger.exception(
            "Falha ao avisar por e-mail o técnico %s da OS %s",
            tecnico.get_username(), chamado.numero_os,
        )
