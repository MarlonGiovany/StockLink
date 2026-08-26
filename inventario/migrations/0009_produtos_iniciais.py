"""Cria os produtos que a empresa já trabalha e classifica os equipamentos
que foram cadastrados antes de o campo "Produto" existir.

A classificação olha para marca + modelo (que hoje já trazem o tipo junto,
ex.: "DESKTOP DELL", "ESTABILIZADOR SMS") e, quando não tem o tipo escrito,
cai nas marcas conhecidas (SAMSUNG, HP, BROTHER... são impressoras).

Nenhum dado é apagado: só preenche o campo novo `produto`.
"""

from django.db import migrations

# nome, ordem, pede_configuracao
PRODUTOS = [
    ("Desktop", 10, True),
    ("Notebook", 20, True),
    ("Monitor", 30, False),
    ("Impressora", 40, False),
    ("Scanner", 50, False),
    ("Estabilizador", 60, False),
    ("Transformador", 70, False),
]

# Palavras que aparecem em marca/modelo → produto. A ordem importa:
# "DESKTOP LENOVO THINKCENTRE" tem que cair em Desktop, não em outro.
POR_PALAVRA = [
    ("TRANSFORMADOR", "Transformador"),
    ("ESTABILIZADOR", "Estabilizador"),
    ("NOBREAK", "Estabilizador"),
    ("DESKTOP", "Desktop"),
    ("THINKCENTRE", "Desktop"),
    ("OPTIPLEX", "Desktop"),
    ("NOTEBOOK", "Notebook"),
    ("IDEAPAD", "Notebook"),
    ("THINKPAD", "Notebook"),
    ("ASPIRE", "Notebook"),
    ("INSPIRON", "Notebook"),
    ("VOSTRO", "Notebook"),
    ("LATITUDE", "Notebook"),
    ("MONITOR", "Monitor"),
    ("SCANNER", "Scanner"),
    ("IMPRESSORA", "Impressora"),
    ("MULTIFUNCIONAL", "Impressora"),
]

# Sem o tipo escrito, a marca resolve: essas só fazem impressora.
MARCAS_IMPRESSORA = [
    "SAMSUNG", "SAMSUMG", "BROTHER", "CANON", "EPSON", "PANTUM",
    "LEXMARK", "XEROX", "RICOH", "KYOCERA", "OKI", "HP",
]


def classificar(marca, modelo):
    texto = f"{marca} {modelo}".upper()
    for palavra, produto in POR_PALAVRA:
        if palavra in texto:
            return produto
    for marca_conhecida in MARCAS_IMPRESSORA:
        if marca_conhecida in texto:
            return "Impressora"
    return None


def preencher(apps, schema_editor):
    Produto = apps.get_model("inventario", "Produto")
    Equipamento = apps.get_model("inventario", "Equipamento")

    por_nome = {}
    for nome, ordem, pede_config in PRODUTOS:
        produto, _ = Produto.objects.get_or_create(
            nome=nome,
            defaults={"ordem": ordem, "pede_configuracao": pede_config, "ativo": True},
        )
        por_nome[nome] = produto

    for equipamento in Equipamento.objects.filter(produto__isnull=True):
        nome = classificar(equipamento.marca, equipamento.modelo)
        if nome:
            equipamento.produto = por_nome[nome]
            equipamento.save(update_fields=["produto"])


def desfazer(apps, schema_editor):
    """Volta atrás sem perder equipamento: só desliga o vínculo e remove
    os produtos que ficaram sem nenhum equipamento."""
    Produto = apps.get_model("inventario", "Produto")
    Equipamento = apps.get_model("inventario", "Equipamento")

    nomes = [nome for nome, _, _ in PRODUTOS]
    Equipamento.objects.filter(produto__nome__in=nomes).update(produto=None)
    Produto.objects.filter(nome__in=nomes, equipamentos__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0008_produto_equipamento_armazenamento_and_more"),
    ]

    operations = [
        migrations.RunPython(preencher, desfazer),
    ]
