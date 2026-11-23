"""Nova área restrita: **Sistema de Tarefas** (``ver_tarefas``).

Mostra a aba *Tarefas*, que abre o Sistema de Tarefas já logado
(ver ``inventario/tarefas_sso.py``). Nenhum perfil ganha a área sozinho: o
Analista libera pessoa por pessoa em "Usuários e permissões".
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0025_perfil_financeiro'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='contrato',
            options={'ordering': ['-data_contrato', '-id'], 'permissions': [('ver_contratos', 'Pode ver a aba de Contratos'), ('ver_pdfs', 'Pode abrir os PDFs anexados'), ('ver_dashboard', 'Pode ver o Dashboard Gerencial'), ('ver_tarefas', 'Pode abrir o Sistema de Tarefas pela aba Tarefas')], 'verbose_name': 'Contrato', 'verbose_name_plural': 'Contratos'},
        ),
    ]
