"""Acrescenta **Tablet** à lista de produtos com que a empresa trabalha.

Entra logo depois de Notebook (ordem 25) e pede configuração — tablet tem
processador, memória e armazenamento, como desktop e notebook. Se algum dia
não fizer sentido, é só desmarcar em /admin/ → Produtos.

Nada é apagado ao desfazer: o produto só some se nenhum equipamento estiver
usando ele.
"""

from django.db import migrations

NOME = "Tablet"
ORDEM = 25


def criar(apps, schema_editor):
    Produto = apps.get_model("inventario", "Produto")
    # `nome` é unique, mas o get_or_create evita quebrar se alguém já tiver
    # cadastrado "Tablet" na mão pelo botão "Adicionar novo produto".
    Produto.objects.get_or_create(
        nome=NOME,
        defaults={"ordem": ORDEM, "pede_configuracao": True, "ativo": True},
    )


def desfazer(apps, schema_editor):
    Produto = apps.get_model("inventario", "Produto")
    Produto.objects.filter(nome=NOME, equipamentos__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0012_chamado_cliente_chamado_prioridade"),
    ]

    operations = [
        migrations.RunPython(criar, desfazer),
    ]
