"""Importa equipamentos do protótipo antigo (equipamentos.json) para o banco.

Uso:
    python manage.py importar_json "C:\\caminho\\equipamentos.json"
"""
import json
from datetime import datetime

from django.core.management.base import BaseCommand

from inventario.models import Equipamento, Manutencao, Movimentacao

STATUS_MAP = {
    "OK": Equipamento.Status.DISPONIVEL,
    "DISPONIVEL": Equipamento.Status.DISPONIVEL,
    "REVISADO": Equipamento.Status.DISPONIVEL,
    "LOCADO": Equipamento.Status.LOCADO,
    "MANUTENCAO": Equipamento.Status.MANUTENCAO,
}


class Command(BaseCommand):
    help = "Importa equipamentos de um arquivo JSON do protótipo antigo."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", type=str, help="Caminho do equipamentos.json")

    def handle(self, *args, **options):
        caminho = options["arquivo"]
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)

        criados, pulados = 0, 0
        for item in dados:
            patrimonio = str(item.get("inf") or "").strip()
            if not patrimonio:
                self.stdout.write(self.style.WARNING("Item sem patrimônio, ignorado."))
                pulados += 1
                continue
            if Equipamento.objects.filter(numero_patrimonio=patrimonio).exists():
                pulados += 1
                continue

            status_orig = str(item.get("status") or "").upper()
            equipamento = Equipamento.objects.create(
                marca=item.get("marca", ""),
                modelo=item.get("modelo", ""),
                numero_serie=str(item.get("serie") or ""),
                numero_patrimonio=patrimonio,
                local=item.get("local", ""),
                status=STATUS_MAP.get(status_orig, Equipamento.Status.DISPONIVEL),
                observacoes=(
                    f"Importado do sistema antigo (status original: {status_orig})."
                    if status_orig not in STATUS_MAP else ""
                ),
            )
            Movimentacao.objects.create(
                equipamento=equipamento,
                tipo=Movimentacao.Tipo.CADASTRO,
                descricao="Importado do protótipo antigo (JSON).",
            )

            for h in item.get("historico", []):
                data = self._parse_data(h.get("data"))
                Manutencao.objects.create(
                    equipamento=equipamento,
                    data=data,
                    descricao=(h.get("servico") or "").strip() or "Manutenção importada",
                )
                Movimentacao.objects.create(
                    equipamento=equipamento,
                    tipo=Movimentacao.Tipo.MANUTENCAO,
                    descricao=f"Manutenção importada: {(h.get('servico') or '').strip()}",
                )
            criados += 1

        self.stdout.write(self.style.SUCCESS(
            f"Importação concluída: {criados} criados, {pulados} ignorados."
        ))

    @staticmethod
    def _parse_data(valor):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(valor).strip(), fmt).date()
            except (ValueError, TypeError):
                continue
        from django.utils import timezone
        return timezone.now().date()
