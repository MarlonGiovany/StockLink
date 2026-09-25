"""Cadastra em lote as máquinas de um cliente, já locadas para ele.

Uso:
    python manage.py importar_maquinas ~/maquinas.csv --cliente 77               # só mostra
    python manage.py importar_maquinas ~/maquinas.csv --cliente 77 --confirmar   # grava

O CSV (separado por ponto e vírgula, com cabeçalho) tem as colunas:
    inf;produto;marca;modelo;serie;local

Cada linha vira:
  - um equipamento com status Locado;
  - uma locação ativa para o cliente, começando hoje, com valor R$ 0,00 e sem
    contrato (os valores e os contratos são ajustados depois, à mão — há
    máquinas cobradas por franquia ou custo por página, sem valor fixo);
  - os registros no histórico de movimentações, como no cadastro manual.

Nada é gravado se alguma linha tiver problema: INF vazio ou repetido, INF ou
número de série que já existe no sistema, ou produto que não existe. Sem
--confirmar, o comando só lista o que faria.

O CSV fica fora do repositório: são dados do cliente, não código.
"""
import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from inventario.models import (
    Cliente,
    Equipamento,
    Locacao,
    Movimentacao,
    Produto,
)

COLUNAS = ("inf", "produto", "marca", "modelo", "serie", "local")


class Command(BaseCommand):
    help = "Cadastra máquinas de um CSV já locadas para um cliente."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="CSV com as máquinas (ver o topo deste arquivo).")
        parser.add_argument("--cliente", type=int, required=True, help="ID do cliente.")
        parser.add_argument(
            "--confirmar", action="store_true",
            help="Grava. Sem isto, só mostra o que faria.",
        )

    def handle(self, *args, arquivo, cliente, confirmar, **options):
        cliente_obj = Cliente.objects.filter(pk=cliente).first()
        if not cliente_obj:
            raise CommandError(f"Cliente {cliente} não existe.")
        linhas = self.le_csv(arquivo)
        produtos = {p.nome: p for p in Produto.objects.all()}

        erros = []
        vistos = set()
        for n, linha in enumerate(linhas, start=2):
            inf = linha["inf"]
            if not inf:
                erros.append(f"linha {n}: sem INF")
            elif inf in vistos:
                erros.append(f"linha {n}: INF {inf} repetido no arquivo")
            elif Equipamento.objects.filter(numero_patrimonio=inf).exists():
                erros.append(f"linha {n}: INF {inf} já existe no sistema")
            vistos.add(inf)
            if linha["serie"] and Equipamento.objects.filter(numero_serie=linha["serie"]).exists():
                erros.append(f"linha {n}: série {linha['serie']} já existe no sistema")
            if linha["produto"] not in produtos:
                erros.append(f"linha {n}: produto '{linha['produto']}' não existe")
            if not linha["marca"] or not linha["modelo"]:
                erros.append(f"linha {n}: sem marca ou modelo")

        hoje = timezone.localdate()
        self.stdout.write(
            f"Cliente: {cliente_obj.pk} — {cliente_obj.nome}\n"
            f"Locação: ativa, início {hoje:%d/%m/%Y}, R$ 0,00, sem contrato\n"
        )
        for linha in linhas:
            self.stdout.write(
                f"  INF {linha['inf']:<8} {linha['produto']:<11} {linha['marca']:<8} "
                f"{linha['modelo']:<11} série {linha['serie']:<12} local: {linha['local']}"
            )
        if erros:
            raise CommandError("Nada foi gravado:\n  " + "\n  ".join(erros))
        if not confirmar:
            self.stdout.write(self.style.WARNING(
                f"\n{len(linhas)} máquina(s) seriam cadastradas. Nada foi gravado — "
                f"rode de novo com --confirmar para aplicar."
            ))
            return

        with transaction.atomic():
            for linha in linhas:
                equipamento = Equipamento.objects.create(
                    produto=produtos[linha["produto"]],
                    marca=linha["marca"],
                    modelo=linha["modelo"],
                    numero_serie=linha["serie"],
                    numero_patrimonio=linha["inf"],
                    local=linha["local"],
                    status=Equipamento.Status.LOCADO,
                )
                Movimentacao.objects.create(
                    equipamento=equipamento, tipo=Movimentacao.Tipo.CADASTRO,
                    descricao=(
                        f"{equipamento.produto} cadastrado em "
                        f"'{equipamento.local or 'sem local'}' (importação em lote)."
                    ),
                )
                locacao = Locacao.objects.create(
                    equipamento=equipamento, cliente=cliente_obj,
                    valor=0, data_inicio=hoje, ativa=True,
                )
                Movimentacao.objects.create(
                    equipamento=equipamento, tipo=Movimentacao.Tipo.LOCACAO,
                    descricao=(
                        f"Locado para {cliente_obj} por R$ {locacao.valor} "
                        f"(início {hoje:%d/%m/%Y}) — importação em lote, sem contrato."
                    ),
                )
        self.stdout.write(self.style.SUCCESS(
            f"\n{len(linhas)} máquina(s) cadastradas e locadas para {cliente_obj.nome}."
        ))

    def le_csv(self, arquivo):
        try:
            with open(arquivo, encoding="utf-8-sig", newline="") as f:
                leitor = csv.DictReader(f, delimiter=";")
                faltando = set(COLUNAS) - set(leitor.fieldnames or [])
                if faltando:
                    raise CommandError(
                        f"Faltam colunas no CSV: {', '.join(sorted(faltando))}. "
                        f"Esperado: {';'.join(COLUNAS)}"
                    )
                linhas = [
                    {c: (linha.get(c) or "").strip() for c in COLUNAS}
                    for linha in leitor
                    if any((v or "").strip() for v in linha.values())
                ]
        except FileNotFoundError:
            raise CommandError(f"Arquivo não encontrado: {arquivo}")
        if not linhas:
            raise CommandError("O CSV não tem nenhuma máquina.")
        return linhas
