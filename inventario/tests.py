"""Testes das telas de Produto (painel de produtos + cadastro com ficha técnica).

Rodam num banco de dados temporário — o db.sqlite3 de verdade não é tocado.
Para rodar:  python manage.py test inventario
"""

import importlib
import json
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError, QuerySet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Aditivo, Chamado, Cliente, Contrato, Equipamento, Locacao, Manutencao,
    Movimentacao, Produto,
)

# A função de classificação mora na migração 0009 (nome começa com dígito,
# por isso o import tem que ser via importlib).
classificar = importlib.import_module(
    "inventario.migrations.0009_produtos_iniciais"
).classificar


class ClassificacaoTests(TestCase):
    """A regra que separou os 47 equipamentos já cadastrados por produto."""

    def test_reconhece_tipo_escrito_na_marca(self):
        casos = [
            ("DESKTOP DELL", "OPTIPLEX3080", "Desktop"),
            ("DESKTOP LENOVO", "THINKCENTRE", "Desktop"),
            ("NOTEBOOK ACER", "ASPIRE 3", "Notebook"),
            ("MONITOR LOG", "P190VH", "Monitor"),
            ("ESTABILIZADOR SMS", "REVOLUTION", "Estabilizador"),
            ("TRANSFORMADOR RAGTECH", "SENSE MICROPROCESOR", "Transformador"),
            ("DEMAPE", "AUTO TRANSFORMADOR BIVOLT", "Transformador"),
        ]
        for marca, modelo, esperado in casos:
            with self.subTest(marca=marca):
                self.assertEqual(classificar(marca, modelo), esperado)

    def test_cai_na_marca_quando_o_tipo_nao_esta_escrito(self):
        casos = [
            ("SAMSUMG", "SL-M4070"),   # typo de SAMSUNG que existe no banco
            ("HP", "LASER 432 FDN"),
            ("MARCA HP", "432"),
            ("BROTHER", "DCP-L2540"),
            ("CANON", "G3110"),
            ("EPSON", "L6270"),
            ("PANTUM", "M7310"),
        ]
        for marca, modelo in casos:
            with self.subTest(marca=marca):
                self.assertEqual(classificar(marca, modelo), "Impressora")

    def test_notebook_sem_a_palavra_notebook(self):
        self.assertEqual(classificar("LENOVO", "IDEAPAD SLIM 3 15IRH10"), "Notebook")

    def test_desconhecido_fica_sem_produto(self):
        self.assertIsNone(classificar("MARCA XPTO", "MODELO 123"))


class BaseLogada(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "teste", "teste@exemplo.com", "senha-de-teste"
        )
        self.client.force_login(self.user)

        # Os 7 produtos já vêm da migração 0009 — pegar (em vez de criar)
        # também serve de prova de que a migração rodou como esperado.
        self.desktop = Produto.objects.get(nome="Desktop")
        self.impressora = Produto.objects.get(nome="Impressora")
        self.scanner = Produto.objects.get(nome="Scanner")
        self.assertTrue(self.desktop.pede_configuracao)
        self.assertTrue(Produto.objects.get(nome="Notebook").pede_configuracao)
        self.assertFalse(self.impressora.pede_configuracao)

        Equipamento.objects.create(
            produto=self.desktop, marca="DELL", modelo="OPTIPLEX",
            numero_patrimonio="1001",
        )
        Equipamento.objects.create(
            produto=self.impressora, marca="HP", modelo="LASER 432",
            numero_patrimonio="1002",
        )
        Equipamento.objects.create(
            produto=self.impressora, marca="SAMSUNG", modelo="SL-M4070",
            numero_patrimonio="1003",
        )


class PainelDeProdutosTests(BaseLogada):
    def test_abre_no_painel_e_nao_na_lista_corrida(self):
        resposta = self.client.get(reverse("equipamento_lista"))
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "inventario/equipamento_produtos.html")

    def test_painel_traz_a_contagem_de_cada_produto(self):
        resposta = self.client.get(reverse("equipamento_lista"))
        contagens = {p.nome: p.qtd for p in resposta.context["produtos"]}
        self.assertEqual(contagens["Desktop"], 1)
        self.assertEqual(contagens["Impressora"], 2)
        self.assertEqual(contagens["Scanner"], 0)
        self.assertEqual(resposta.context["total_geral"], 3)

    def test_produto_vazio_continua_aparecendo(self):
        resposta = self.client.get(reverse("equipamento_lista"))
        nomes = [p.nome for p in resposta.context["produtos"]]
        self.assertIn("Scanner", nomes)

    def test_filtrar_por_produto_mostra_so_aquele_produto(self):
        resposta = self.client.get(
            reverse("equipamento_lista"), {"produto": self.impressora.pk}
        )
        self.assertTemplateUsed(resposta, "inventario/equipamento_lista.html")
        self.assertEqual(resposta.context["total"], 2)
        self.assertEqual(resposta.context["produto_atual"], self.impressora)

    def test_todos_mostra_a_lista_completa(self):
        resposta = self.client.get(reverse("equipamento_lista"), {"produto": "todos"})
        self.assertTemplateUsed(resposta, "inventario/equipamento_lista.html")
        self.assertEqual(resposta.context["total"], 3)
        self.assertIsNone(resposta.context["produto_atual"])

    def test_busca_pula_o_painel(self):
        resposta = self.client.get(reverse("equipamento_lista"), {"q": "OPTIPLEX"})
        self.assertTemplateUsed(resposta, "inventario/equipamento_lista.html")
        self.assertEqual(resposta.context["total"], 1)

    def test_filtro_de_status_pula_o_painel(self):
        resposta = self.client.get(
            reverse("equipamento_lista"), {"status": "DISPONIVEL"}
        )
        self.assertTemplateUsed(resposta, "inventario/equipamento_lista.html")

    def test_status_junto_com_produto_nao_perde_o_produto(self):
        resposta = self.client.get(
            reverse("equipamento_lista"),
            {"produto": self.impressora.pk, "status": "DISPONIVEL"},
        )
        self.assertEqual(resposta.context["total"], 2)
        self.assertEqual(resposta.context["produto_atual"], self.impressora)

    def test_busca_encontra_pelo_nome_do_produto(self):
        resposta = self.client.get(
            reverse("equipamento_lista"), {"q": "Impressora"}
        )
        self.assertEqual(resposta.context["total"], 2)


class CadastroComProdutoTests(BaseLogada):
    def dados_base(self, **extra):
        dados = {
            "produto": self.desktop.pk,
            "marca": "DELL", "modelo": "OPTIPLEX 7010",
            "numero_serie": "", "numero_patrimonio": "9001",
            "processador": "", "memoria_ram": "", "armazenamento": "",
            "valor_compra": "", "data_aquisicao": "",
            "fornecedor": "", "local": "INFORLINK",
            "status": "DISPONIVEL", "observacoes": "",
        }
        dados.update(extra)
        return dados

    def test_produto_e_obrigatorio(self):
        resposta = self.client.post(
            reverse("equipamento_novo"), self.dados_base(produto="")
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("produto", resposta.context["form"].errors)
        self.assertFalse(Equipamento.objects.filter(numero_patrimonio="9001").exists())

    def test_desktop_salva_a_ficha_tecnica(self):
        resposta = self.client.post(
            reverse("equipamento_novo"),
            self.dados_base(
                processador="Intel Core i5-10500",
                memoria_ram="8 GB DDR4",
                armazenamento="SSD 256 GB",
            ),
        )
        self.assertEqual(resposta.status_code, 302)
        eq = Equipamento.objects.get(numero_patrimonio="9001")
        self.assertEqual(eq.produto, self.desktop)
        self.assertEqual(eq.processador, "Intel Core i5-10500")
        self.assertEqual(eq.memoria_ram, "8 GB DDR4")
        self.assertEqual(eq.armazenamento, "SSD 256 GB")

    def test_produto_sem_configuracao_nao_guarda_ficha_tecnica(self):
        """Se o usuário digitou a ficha e depois trocou para Impressora,
        os três campos não podem ficar salvos com lixo."""
        self.client.post(
            reverse("equipamento_novo"),
            self.dados_base(
                produto=self.impressora.pk,
                numero_patrimonio="9002",
                processador="Intel Core i7",
                memoria_ram="16 GB",
                armazenamento="SSD 512 GB",
            ),
        )
        eq = Equipamento.objects.get(numero_patrimonio="9002")
        self.assertEqual(eq.produto, self.impressora)
        self.assertEqual(eq.processador, "")
        self.assertEqual(eq.memoria_ram, "")
        self.assertEqual(eq.armazenamento, "")

    def test_formulario_informa_quais_produtos_pedem_ficha_tecnica(self):
        resposta = self.client.get(reverse("equipamento_novo"))
        ids = json.loads(resposta.context["produtos_config_json"])
        self.assertIn(self.desktop.pk, ids)
        self.assertNotIn(self.impressora.pk, ids)

    def test_vindo_do_painel_o_produto_ja_vem_escolhido(self):
        resposta = self.client.get(
            reverse("equipamento_novo"), {"produto": self.desktop.pk}
        )
        self.assertEqual(
            str(resposta.context["form"].initial.get("produto")), str(self.desktop.pk)
        )

    def test_editar_mantem_o_produto(self):
        eq = Equipamento.objects.get(numero_patrimonio="1001")
        resposta = self.client.get(reverse("equipamento_editar", args=[eq.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["form"].instance.produto, self.desktop)


class ProdutoNovoTests(BaseLogada):
    def test_cria_produto_via_botao_e_devolve_json(self):
        resposta = self.client.post(
            reverse("produto_novo"), {"nome": "Projetor"},
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertTrue(dados["ok"])
        self.assertEqual(dados["nome"], "Projetor")
        self.assertFalse(dados["pede_configuracao"])
        self.assertTrue(Produto.objects.filter(nome="Projetor").exists())

    def test_produto_novo_entra_no_fim_da_lista(self):
        self.client.post(
            reverse("produto_novo"), {"nome": "Projetor"},
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        novo = Produto.objects.get(nome="Projetor")
        self.assertGreater(novo.ordem, self.scanner.ordem)
        self.assertEqual(Produto.objects.last(), novo)

    def test_nao_deixa_repetir_produto_ignorando_maiuscula(self):
        resposta = self.client.post(
            reverse("produto_novo"), {"nome": "impressora"},
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        self.assertEqual(resposta.status_code, 400)
        dados = resposta.json()
        self.assertFalse(dados["ok"])
        self.assertIn("já existe", dados["erro"])
        self.assertEqual(Produto.objects.filter(nome__iexact="impressora").count(), 1)

    def test_nome_vazio_da_erro(self):
        resposta = self.client.post(
            reverse("produto_novo"), {"nome": "   "},
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(resposta.json()["ok"])

    def test_tira_espaco_sobrando_do_nome(self):
        self.client.post(
            reverse("produto_novo"), {"nome": "  Nobreak  "},
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        self.assertTrue(Produto.objects.filter(nome="Nobreak").exists())

    def test_sem_javascript_redireciona_com_o_produto_escolhido(self):
        resposta = self.client.post(reverse("produto_novo"), {"nome": "Projetor"})
        novo = Produto.objects.get(nome="Projetor")
        self.assertRedirects(
            resposta, f"{reverse('equipamento_novo')}?produto={novo.pk}"
        )

    def test_operador_sem_permissao_nao_cria_produto(self):
        sem_perm = get_user_model().objects.create_user("zezinho", password="x")
        self.client.force_login(sem_perm)
        resposta = self.client.post(
            reverse("produto_novo"), {"nome": "Projetor"},
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(Produto.objects.filter(nome="Projetor").exists())


class ProtecaoDosDadosTests(BaseLogada):
    def test_nao_apaga_produto_que_tem_equipamento(self):
        with self.assertRaises(ProtectedError):
            self.impressora.delete()
        self.assertTrue(Produto.objects.filter(pk=self.impressora.pk).exists())

    def test_produto_vazio_pode_ser_apagado(self):
        self.scanner.delete()
        self.assertFalse(Produto.objects.filter(nome="Scanner").exists())

    def test_precisa_estar_logado(self):
        self.client.logout()
        resposta = self.client.get(reverse("equipamento_lista"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/login/", resposta.url)


class ContratoCompartilhadoTests(BaseLogada):
    """Um mesmo contrato atendendo várias máquinas do mesmo cliente.

    É o caso real da RODOSERGIPE, que tinha um contrato por máquina.
    """

    def setUp(self):
        super().setUp()
        self.rodo = Cliente.objects.create(nome="RODOSERGIPE")
        self.outro = Cliente.objects.create(nome="HOSPITAL RENASCENCA")

        self.contrato_rodo = Contrato.objects.create(
            numero="03", cliente=self.rodo, data_contrato="2026-08-01"
        )
        self.contrato_outro = Contrato.objects.create(
            numero="99", cliente=self.outro, data_contrato="2026-08-02"
        )

        self.maquina1 = Equipamento.objects.get(numero_patrimonio="1002")
        self.maquina2 = Equipamento.objects.get(numero_patrimonio="1003")

    def dados_locacao(self, **extra):
        dados = {
            "cliente": self.rodo.pk, "contrato": "", "valor": "250.00",
            "data_inicio": "2026-08-05", "data_fim": "",
            "ativa": "on", "observacoes": "",
        }
        dados.update(extra)
        return dados

    def test_um_contrato_recebe_duas_maquinas(self):
        for maquina in (self.maquina1, self.maquina2):
            resposta = self.client.post(
                reverse("locacao_nova", args=[maquina.pk]),
                self.dados_locacao(contrato=self.contrato_rodo.pk),
            )
            self.assertEqual(resposta.status_code, 302)

        self.assertEqual(self.contrato_rodo.locacoes.count(), 2)
        self.assertEqual(Contrato.objects.count(), 2)  # nenhum contrato novo

    def test_nao_deixa_usar_contrato_de_outro_cliente(self):
        resposta = self.client.post(
            reverse("locacao_nova", args=[self.maquina1.pk]),
            self.dados_locacao(contrato=self.contrato_outro.pk),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("contrato", resposta.context["form"].errors)
        self.assertFalse(Locacao.objects.filter(equipamento=self.maquina1).exists())

    def test_locacao_sem_contrato_continua_valendo(self):
        resposta = self.client.post(
            reverse("locacao_nova", args=[self.maquina1.pk]), self.dados_locacao()
        )
        self.assertEqual(resposta.status_code, 302)
        locacao = Locacao.objects.get(equipamento=self.maquina1)
        self.assertIsNone(locacao.contrato)

    def criar_locacao_sem_contrato(self, maquina):
        self.client.post(
            reverse("locacao_nova", args=[maquina.pk]), self.dados_locacao()
        )
        return Locacao.objects.get(equipamento=maquina)

    def test_vincula_locacao_existente_a_contrato_existente(self):
        locacao = self.criar_locacao_sem_contrato(self.maquina1)
        resposta = self.client.post(
            reverse("locacao_vincular_contrato", args=[locacao.pk]),
            {"contrato": self.contrato_rodo.pk},
        )
        self.assertEqual(resposta.status_code, 302)
        locacao.refresh_from_db()
        self.assertEqual(locacao.contrato, self.contrato_rodo)

    def test_vincular_a_contrato_de_outro_cliente_e_recusado(self):
        locacao = self.criar_locacao_sem_contrato(self.maquina1)
        self.client.post(
            reverse("locacao_vincular_contrato", args=[locacao.pk]),
            {"contrato": self.contrato_outro.pk},
        )
        locacao.refresh_from_db()
        self.assertIsNone(locacao.contrato)

    def test_ficha_do_equipamento_lista_contratos_do_cliente(self):
        locacao = self.criar_locacao_sem_contrato(self.maquina1)
        resposta = self.client.get(
            reverse("equipamento_detalhe", args=[self.maquina1.pk])
        )
        contratos = list(resposta.context["contratos_do_cliente"])
        self.assertIn(self.contrato_rodo, contratos)
        self.assertNotIn(self.contrato_outro, contratos)
        self.assertEqual(resposta.context["locacao_ativa"], locacao)

    def test_sem_contrato_oferece_vincular_existente_E_criar_novo(self):
        self.criar_locacao_sem_contrato(self.maquina1)
        html = self.client.get(
            reverse("equipamento_detalhe", args=[self.maquina1.pk])
        ).content.decode()
        self.assertIn('name="contrato"', html)          # escolher um que já existe
        self.assertIn("Criar contrato novo", html)      # ou criar do zero

    def test_cliente_sem_contrato_so_oferece_criar_novo(self):
        Contrato.objects.filter(cliente=self.rodo).delete()
        self.criar_locacao_sem_contrato(self.maquina1)
        html = self.client.get(
            reverse("equipamento_detalhe", args=[self.maquina1.pk])
        ).content.decode()
        self.assertNotIn('name="contrato"', html)
        self.assertIn("Criar contrato novo", html)

    def test_contrato_ja_vinculado_nao_aparece_como_opcao_de_troca(self):
        locacao = self.criar_locacao_sem_contrato(self.maquina1)
        self.client.post(
            reverse("locacao_vincular_contrato", args=[locacao.pk]),
            {"contrato": self.contrato_rodo.pk},
        )
        resposta = self.client.get(
            reverse("equipamento_detalhe", args=[self.maquina1.pk])
        )
        self.assertNotIn(
            self.contrato_rodo, list(resposta.context["contratos_do_cliente"])
        )

    def test_pagina_do_contrato_mostra_as_maquinas(self):
        for maquina in (self.maquina1, self.maquina2):
            self.client.post(
                reverse("locacao_nova", args=[maquina.pk]),
                self.dados_locacao(contrato=self.contrato_rodo.pk),
            )
        resposta = self.client.get(
            reverse("contrato_detalhe", args=[self.contrato_rodo.pk])
        )
        self.assertEqual(resposta.context["qtd_maquinas"], 2)
        patrimonios = {
            l.equipamento.numero_patrimonio for l in resposta.context["locacoes"]
        }
        self.assertEqual(patrimonios, {"1002", "1003"})

    def test_lista_de_contratos_conta_as_maquinas(self):
        self.client.post(
            reverse("locacao_nova", args=[self.maquina1.pk]),
            self.dados_locacao(contrato=self.contrato_rodo.pk),
        )
        resposta = self.client.get(reverse("contrato_lista"))
        por_numero = {c.numero: c.qtd_maquinas for c in resposta.context["contratos"]}
        self.assertEqual(por_numero["03"], 1)
        self.assertEqual(por_numero["99"], 0)

    def test_formulario_oferece_contratos_marcados_com_o_cliente(self):
        """O `data-cliente` em cada opção é o que faz a tela filtrar."""
        resposta = self.client.get(reverse("locacao_nova", args=[self.maquina1.pk]))
        html = resposta.content.decode()
        self.assertIn(f'data-cliente="{self.rodo.pk}"', html)
        self.assertIn(f'data-cliente="{self.outro.pk}"', html)

    def test_encerrar_locacao_nao_desfaz_o_vinculo_do_contrato(self):
        self.client.post(
            reverse("locacao_nova", args=[self.maquina1.pk]),
            self.dados_locacao(contrato=self.contrato_rodo.pk),
        )
        locacao = Locacao.objects.get(equipamento=self.maquina1)
        self.client.post(reverse("locacao_encerrar", args=[locacao.pk]))
        locacao.refresh_from_db()
        self.assertFalse(locacao.ativa)
        self.assertEqual(locacao.contrato, self.contrato_rodo)


class NumeroDoAditivoConcorrenteTests(BaseLogada):
    """Duas pessoas salvando aditivo no mesmo contrato ao mesmo tempo.

    Se a leitura do "próximo número" já estiver desatualizada quando a
    segunda tentativa for gravada, a constraint única (contrato, numero)
    rejeita — a view precisa recalcular e tentar de novo, não estourar 500.
    """

    def setUp(self):
        super().setUp()
        self.cliente = Cliente.objects.create(nome="RODOSERGIPE")
        self.contrato = Contrato.objects.create(
            numero="10", cliente=self.cliente, data_contrato="2026-08-01"
        )
        # Simula que outra pessoa acabou de gravar o aditivo 1 bem no
        # instante em que esta requisição ainda vai ler o "próximo".
        Aditivo.objects.create(contrato=self.contrato, numero=1, descricao="x")

    def test_recalcula_numero_apos_colisao_em_vez_de_quebrar(self):
        chamadas = {"n": 0}
        original_aggregate = QuerySet.aggregate

        def aggregate_com_leitura_desatualizada(self_qs, *args, **kwargs):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                return {"m": 0}  # já não vale mais: o aditivo 1 já existe
            return original_aggregate(self_qs, *args, **kwargs)

        with mock.patch.object(
            QuerySet, "aggregate", aggregate_com_leitura_desatualizada
        ):
            resposta = self.client.post(
                reverse("aditivo_novo", args=[self.contrato.pk]),
                {
                    "tipo": Aditivo.Tipo.ADICAO, "descricao": "Nova cláusula",
                    "valor": "", "data": "2026-09-01", "observacoes": "",
                    "equipamentos": [],
                },
            )
        self.assertEqual(resposta.status_code, 302)
        numeros = set(
            Aditivo.objects.filter(contrato=self.contrato)
            .values_list("numero", flat=True)
        )
        self.assertEqual(numeros, {1, 2})

    def test_desiste_com_mensagem_amigavel_se_colidir_sempre(self):
        def aggregate_sempre_desatualizado(self_qs, *args, **kwargs):
            return {"m": 0}

        with mock.patch.object(
            QuerySet, "aggregate", aggregate_sempre_desatualizado
        ):
            resposta = self.client.post(
                reverse("aditivo_novo", args=[self.contrato.pk]),
                {
                    "tipo": Aditivo.Tipo.ADICAO, "descricao": "Nova cláusula",
                    "valor": "", "data": "2026-09-01", "observacoes": "",
                    "equipamentos": [],
                },
            )
        self.assertEqual(resposta.status_code, 200)  # não é 500
        self.assertContains(resposta, "Tente novamente")
        self.assertEqual(Aditivo.objects.filter(contrato=self.contrato).count(), 1)


class LocacaoDuplicadaTests(BaseLogada):
    """Não pode existir uma 2ª locação ativa para o mesmo equipamento.

    A tela esconde o botão "Registrar locação" quando já existe uma ativa,
    mas isso não impede um POST direto para a URL — a trava de verdade tem
    que estar no servidor.
    """

    def setUp(self):
        super().setUp()
        self.cliente1 = Cliente.objects.create(nome="RODOSERGIPE")
        self.cliente2 = Cliente.objects.create(nome="HOSPITAL RENASCENCA")
        self.maquina = Equipamento.objects.get(numero_patrimonio="1002")
        self.locacao_atual = Locacao.objects.create(
            equipamento=self.maquina, cliente=self.cliente1,
            valor="200.00", data_inicio="2026-08-01", ativa=True,
        )

    def dados_locacao(self, **extra):
        dados = {
            "cliente": self.cliente2.pk, "contrato": "", "valor": "300.00",
            "data_inicio": "2026-09-01", "data_fim": "",
            "ativa": "on", "observacoes": "",
        }
        dados.update(extra)
        return dados

    def test_recusa_segunda_locacao_ativa_via_post_direto(self):
        resposta = self.client.post(
            reverse("locacao_nova", args=[self.maquina.pk]), self.dados_locacao()
        )
        self.assertEqual(resposta.status_code, 200)  # não redireciona: erro
        self.assertContains(resposta, "já está locado para")
        self.assertEqual(
            Locacao.objects.filter(equipamento=self.maquina, ativa=True).count(), 1
        )
        self.assertEqual(
            Locacao.objects.filter(equipamento=self.maquina).count(), 1
        )

    def test_permite_registrar_locacao_encerrada_como_historico(self):
        """Marcar a nova locação como não-ativa não conflita com a atual."""
        resposta = self.client.post(
            reverse("locacao_nova", args=[self.maquina.pk]),
            self.dados_locacao(ativa=""),
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Locacao.objects.filter(equipamento=self.maquina).count(), 2)

    def test_libera_nova_locacao_apos_encerrar_a_atual(self):
        self.client.post(reverse("locacao_encerrar", args=[self.locacao_atual.pk]))
        resposta = self.client.post(
            reverse("locacao_nova", args=[self.maquina.pk]), self.dados_locacao()
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            Locacao.objects.filter(equipamento=self.maquina, ativa=True).count(), 1
        )


class ExclusaoDeEquipamentoTests(BaseLogada):
    """Equipamento locado não pode ser excluído.

    Igual à locação duplicada: o botão "Excluir" some da tela quando o
    equipamento está locado, mas a trava real precisa estar no servidor.
    """

    def setUp(self):
        super().setUp()
        self.cliente = Cliente.objects.create(nome="RODOSERGIPE")
        self.maquina = Equipamento.objects.get(numero_patrimonio="1002")
        self.locacao = Locacao.objects.create(
            equipamento=self.maquina, cliente=self.cliente,
            valor="200.00", data_inicio="2026-08-01", ativa=True,
        )

    def test_recusa_excluir_equipamento_locado_via_post_direto(self):
        resposta = self.client.post(
            reverse("equipamento_excluir", args=[self.maquina.pk])
        )
        self.assertRedirects(
            resposta, reverse("equipamento_detalhe", args=[self.maquina.pk])
        )
        self.assertTrue(Equipamento.objects.filter(pk=self.maquina.pk).exists())

    def test_tela_de_confirmacao_nao_mostra_botao_de_excluir_se_locado(self):
        resposta = self.client.get(
            reverse("equipamento_excluir", args=[self.maquina.pk])
        )
        self.assertNotContains(resposta, "Sim, excluir")

    def test_exclui_normalmente_depois_de_encerrar_a_locacao(self):
        self.client.post(reverse("locacao_encerrar", args=[self.locacao.pk]))
        resposta = self.client.post(
            reverse("equipamento_excluir", args=[self.maquina.pk])
        )
        self.assertRedirects(resposta, reverse("equipamento_lista"))
        self.assertFalse(Equipamento.objects.filter(pk=self.maquina.pk).exists())


class BuscaDeClienteTests(BaseLogada):
    """O filtro de busca da aba Clientes."""

    def setUp(self):
        super().setUp()
        Cliente.objects.create(nome="RODOVIÁRIO SANTA MARIA")
        Cliente.objects.create(nome="SANTA CASA DE MISERICÓRDIA")
        Cliente.objects.create(nome="PADARIA DO JOÃO")

    def nomes(self, **get):
        resposta = self.client.get(reverse("cliente_lista"), get)
        return {c.nome for c in resposta.context["clientes"]}

    def test_sem_busca_traz_todos(self):
        self.assertEqual(len(self.nomes()), 3)

    def test_busca_por_parte_do_nome(self):
        self.assertEqual(
            self.nomes(q="SANTA"),
            {"RODOVIÁRIO SANTA MARIA", "SANTA CASA DE MISERICÓRDIA"},
        )

    def test_busca_ignora_maiuscula(self):
        self.assertEqual(self.nomes(q="padaria"), {"PADARIA DO JOÃO"})

    def test_busca_sem_resultado_nao_quebra(self):
        resposta = self.client.get(reverse("cliente_lista"), {"q": "XPTO"})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["total"], 0)
        self.assertIn("XPTO", resposta.content.decode())


class ProdutoTabletTests(BaseLogada):
    """A migração 0013 acrescentou Tablet à lista de produtos."""

    def test_tablet_existe_ativo_e_pede_configuracao(self):
        tablet = Produto.objects.get(nome="Tablet")
        self.assertTrue(tablet.ativo)
        self.assertTrue(tablet.pede_configuracao)

    def test_tablet_entra_depois_de_notebook_e_antes_de_monitor(self):
        ordem = list(
            Produto.objects.order_by("ordem", "nome").values_list("nome", flat=True)
        )
        self.assertEqual(
            ordem[ordem.index("Notebook") + 1], "Tablet"
        )
        self.assertEqual(ordem[ordem.index("Tablet") + 1], "Monitor")

    def test_tablet_aparece_no_formulario_de_equipamento(self):
        html = self.client.get(reverse("equipamento_novo")).content.decode()
        self.assertIn("Tablet", html)


class ContagemDeMaquinasDoContratoTests(BaseLogada):
    """Máquina devolvida (locação encerrada) não conta no total do contrato."""

    def setUp(self):
        super().setUp()
        self.cliente = Cliente.objects.create(nome="RODOVIÁRIO")
        self.contrato = Contrato.objects.create(numero="77", cliente=self.cliente)
        self.m1, self.m2 = (
            Equipamento.objects.get(numero_patrimonio="1002"),
            Equipamento.objects.get(numero_patrimonio="1003"),
        )
        for maquina in (self.m1, self.m2):
            Locacao.objects.create(
                equipamento=maquina, cliente=self.cliente, contrato=self.contrato,
                valor="250.00", data_inicio="2026-08-05", ativa=True,
            )

    def encerra_uma(self):
        locacao = Locacao.objects.get(equipamento=self.m2)
        locacao.ativa = False
        locacao.save(update_fields=["ativa"])

    def test_com_as_duas_ativas_conta_duas(self):
        self.assertEqual(self.contrato.maquinas_ativas, 2)

    def test_encerrada_sai_da_conta_mas_fica_no_historico(self):
        self.encerra_uma()
        self.assertEqual(self.contrato.maquinas_ativas, 1)
        self.assertEqual(self.contrato.locacoes.count(), 2)

    def test_ficha_do_contrato_conta_so_as_ativas(self):
        self.encerra_uma()
        resposta = self.client.get(reverse("contrato_detalhe", args=[self.contrato.pk]))
        self.assertEqual(resposta.context["qtd_maquinas"], 1)
        self.assertEqual(resposta.context["qtd_encerradas"], 1)
        # A encerrada continua listada abaixo, como histórico
        self.assertEqual(len(resposta.context["locacoes"]), 2)

    def test_lista_de_contratos_conta_so_as_ativas(self):
        self.encerra_uma()
        resposta = self.client.get(reverse("contrato_lista"))
        por_numero = {c.numero: c.qtd_maquinas for c in resposta.context["contratos"]}
        self.assertEqual(por_numero["77"], 1)


class BaseComChamado(BaseLogada):
    """Um cliente com máquina locada e um chamado aberto para ela."""

    def setUp(self):
        super().setUp()
        self.cliente = Cliente.objects.create(nome="RODOVIÁRIO")
        self.outro_cliente = Cliente.objects.create(nome="PADARIA")
        self.maquina = Equipamento.objects.get(numero_patrimonio="1002")
        self.maquina_outro = Equipamento.objects.get(numero_patrimonio="1003")
        for maquina, cliente in (
            (self.maquina, self.cliente), (self.maquina_outro, self.outro_cliente)
        ):
            Locacao.objects.create(
                equipamento=maquina, cliente=cliente, valor="250.00",
                data_inicio="2026-08-05", ativa=True,
            )
        self.chamado = Chamado.objects.create(
            cliente=self.cliente, equipamento=self.maquina,
            descricao="Não liga.", tecnico=self.user, aberto_por=self.user,
            prioridade=Chamado.Prioridade.URGENTE,
        )
        self.chamado_outro = Chamado.objects.create(
            cliente=self.outro_cliente, equipamento=self.maquina_outro,
            descricao="Papel enroscado.", tecnico=self.user, aberto_por=self.user,
        )


class FiltroDeChamadoPorClienteTests(BaseComChamado):
    def test_sem_filtro_traz_os_dois(self):
        resposta = self.client.get(reverse("chamado_lista"))
        self.assertEqual(resposta.context["total"], 2)

    def test_filtra_pelo_cliente_escolhido(self):
        resposta = self.client.get(
            reverse("chamado_lista"), {"cliente": self.cliente.pk}
        )
        self.assertEqual(
            [c.pk for c in resposta.context["chamados"]], [self.chamado.pk]
        )

    def test_a_lista_de_clientes_do_filtro_so_tem_quem_teve_chamado(self):
        Cliente.objects.create(nome="SEM CHAMADO")
        resposta = self.client.get(reverse("chamado_lista"))
        nomes = {c.nome for c in resposta.context["clientes"]}
        self.assertEqual(nomes, {"RODOVIÁRIO", "PADARIA"})

    def test_historico_por_tecnico_tambem_filtra_por_cliente(self):
        resposta = self.client.get(
            reverse("chamado_historico"), {"cliente": self.outro_cliente.pk}
        )
        self.assertEqual(resposta.context["total"], 1)


class PainelDaAreaTecnicaTests(BaseComChamado):
    def envelhece(self, chamado, horas):
        """Recua a abertura do chamado. `aberto_em` é auto_now_add, então só
        um update() direto no banco consegue mexer nele."""
        quando = timezone.now() - timedelta(hours=horas)
        Chamado.objects.filter(pk=chamado.pk).update(aberto_em=quando)
        chamado.refresh_from_db()

    def test_o_painel_manda_o_ultimo_id_para_o_alerta_sonoro(self):
        resposta = self.client.get(reverse("chamado_painel"))
        self.assertEqual(resposta.context["ultimo_id"], self.chamado_outro.pk)
        html = resposta.content.decode()
        # O <meta refresh> saiu: recarregar a página matava o som liberado
        self.assertNotIn("http-equiv=\"refresh\"", html)

    def test_o_painel_nao_pede_para_ativar_o_som(self):
        """O som é automático — a TV fica transmitindo sem ninguém por perto."""
        html = self.client.get(reverse("chamado_painel")).content.decode()
        self.assertNotIn("Ativar som", html)
        self.assertIn("Clique em qualquer lugar para ligar o som", html)

    def test_dados_do_painel_vem_em_json_com_os_cartoes(self):
        resposta = self.client.get(reverse("chamado_painel_dados"))
        dados = json.loads(resposta.content)
        self.assertEqual(dados["total"], 2)
        self.assertEqual(dados["urgentes"], 1)
        self.assertEqual(dados["ultimo_id"], self.chamado_outro.pk)
        self.assertIn(f"OS {self.chamado.numero_os}", dados["html"])
        self.assertIn("Aberto", dados["html"])

    def test_chamado_novo_aumenta_o_ultimo_id(self):
        antes = json.loads(
            self.client.get(reverse("chamado_painel_dados")).content
        )["ultimo_id"]
        novo = Chamado.objects.create(
            cliente=self.cliente, equipamento=self.maquina,
            descricao="Outro problema.", tecnico=self.user,
        )
        depois = json.loads(
            self.client.get(reverse("chamado_painel_dados")).content
        )
        self.assertGreater(depois["ultimo_id"], antes)
        self.assertEqual(depois["ultimo_id"], novo.pk)

    def test_chamado_recente_nao_conta_como_atrasado(self):
        resposta = self.client.get(reverse("chamado_painel"))
        self.assertEqual(resposta.context["atrasados"], 0)
        self.assertFalse(self.chamado.atrasado)

    def test_passou_de_24h_em_aberto_vira_atrasado(self):
        self.envelhece(self.chamado, horas=25)
        self.assertTrue(self.chamado.atrasado)
        dados = json.loads(
            self.client.get(reverse("chamado_painel_dados")).content
        )
        self.assertEqual(dados["atrasados"], 1)
        self.assertIn("MAIS DE 24H EM ABERTO", dados["html"])

    def test_exatamente_24h_ja_conta(self):
        self.envelhece(self.chamado, horas=24)
        self.assertTrue(self.chamado.atrasado)

    def test_23h_ainda_nao_conta(self):
        self.envelhece(self.chamado, horas=23)
        self.assertFalse(self.chamado.atrasado)

    def test_chamado_encerrado_nunca_conta_como_atrasado(self):
        self.envelhece(self.chamado, horas=50)
        self.chamado.status = Chamado.Status.ENCERRADO
        self.chamado.realizado = "Resolvido."
        self.chamado.encerrado_em = timezone.now()
        self.chamado.save()
        self.assertFalse(self.chamado.atrasado)
        dados = json.loads(
            self.client.get(reverse("chamado_painel_dados")).content
        )
        self.assertEqual(dados["atrasados"], 0)

    def test_atrasado_vai_para_o_topo_mesmo_sendo_leve(self):
        """Esperar um dia inteiro é pior que a urgência escrita na abertura."""
        self.chamado_outro.prioridade = Chamado.Prioridade.LEVE
        self.chamado_outro.save(update_fields=["prioridade"])
        self.envelhece(self.chamado_outro, horas=30)
        resposta = self.client.get(reverse("chamado_painel"))
        ordem = [c.pk for c in resposta.context["chamados"]]
        # o urgente self.chamado fica atrás do leve que está parado há 30h
        self.assertEqual(ordem[0], self.chamado_outro.pk)

    def test_encerrado_hoje_aparece_no_painel_com_o_status(self):
        self.chamado_outro.status = Chamado.Status.ENCERRADO
        self.chamado_outro.realizado = "Retirado o papel."
        self.chamado_outro.encerrado_em = timezone.now()
        self.chamado_outro.save()
        dados = json.loads(
            self.client.get(reverse("chamado_painel_dados")).content
        )
        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["qtd_encerrados"], 1)
        self.assertIn("Encerrado", dados["html"])


class OrdemDeServicoImpressaTests(BaseComChamado):
    """A folha física tem que sair com o mesmo número da OS do sistema."""

    def test_o_documento_traz_o_numero_da_os(self):
        resposta = self.client.get(reverse("chamado_imprimir", args=[self.chamado.pk]))
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        self.assertEqual(html.count(self.chamado.numero_os) >= 3, True)
        self.assertIn("Ordem de Serviço Nº", html)

    def test_o_documento_traz_os_dados_ja_preenchidos(self):
        self.cliente.documento = "12.345.678/0001-90"
        self.cliente.telefone = "(82) 99999-0000"
        self.cliente.save()
        html = self.client.get(
            reverse("chamado_imprimir", args=[self.chamado.pk])
        ).content.decode()
        for esperado in (
            "RODOVIÁRIO", "12.345.678/0001-90", "(82) 99999-0000",
            self.maquina.numero_patrimonio, "HP", "LASER 432",
            "Não liga.", self.user.get_username(),
        ):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, html)

    def test_o_documento_tem_os_campos_para_o_tecnico_preencher(self):
        html = self.client.get(
            reverse("chamado_imprimir", args=[self.chamado.pk])
        ).content.decode()
        for secao in (
            "Serviço realizado", "Troca de peça", "Peça substituída",
            "Observações", "Assinatura do técnico",
            "Assinatura do cliente / acompanhante",
        ):
            with self.subTest(secao=secao):
                self.assertIn(secao, html)

    def test_so_quem_esta_logado_imprime(self):
        self.client.logout()
        resposta = self.client.get(reverse("chamado_imprimir", args=[self.chamado.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/login/", resposta["Location"])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class EncerramentoDaOrdemDeServicoTests(BaseComChamado):
    """O encerramento carrega o que foi escrito na OS física."""

    def dados(self, **extra):
        base = {
            "realizado": "Trocada a fonte queimada.",
            "peca_substituida": "",
            "observacoes": "",
        }
        base.update(extra)
        return base

    def encerra(self, **extra):
        return self.client.post(
            reverse("chamado_detalhe", args=[self.chamado.pk]), self.dados(**extra)
        )

    def test_encerra_sem_troca_de_peca(self):
        self.assertEqual(self.encerra().status_code, 302)
        self.chamado.refresh_from_db()
        self.assertTrue(self.chamado.encerrado)
        self.assertFalse(self.chamado.houve_troca_peca)
        self.assertEqual(self.chamado.peca_texto, "Não houve troca de peça")

    def test_troca_de_peca_exige_dizer_qual_peca(self):
        resposta = self.encerra(houve_troca_peca="on")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("peca_substituida", resposta.context["form"].errors)
        self.chamado.refresh_from_db()
        self.assertFalse(self.chamado.encerrado)

    def test_grava_a_peca_substituida_e_as_observacoes(self):
        self.encerra(
            houve_troca_peca="on", peca_substituida="Fonte 500W",
            observacoes="Cliente pediu orçamento de SSD.",
        )
        self.chamado.refresh_from_db()
        self.assertTrue(self.chamado.houve_troca_peca)
        self.assertEqual(self.chamado.peca_substituida, "Fonte 500W")
        self.assertEqual(self.chamado.peca_texto, "Fonte 500W")
        self.assertIn("SSD", self.chamado.observacoes)

    def test_peca_escrita_sem_marcar_a_caixinha_marca_sozinho(self):
        """Esquecer de marcar é comum; perder a informação da peça, não."""
        self.encerra(peca_substituida="Toner preto")
        self.chamado.refresh_from_db()
        self.assertTrue(self.chamado.houve_troca_peca)

    def test_encerra_ja_anexando_a_os_digitalizada(self):
        pdf = SimpleUploadedFile(
            "os-0001.pdf", b"%PDF-1.4 assinado", content_type="application/pdf"
        )
        self.encerra(arquivo_os=pdf)
        self.chamado.refresh_from_db()
        self.assertTrue(self.chamado.encerrado)
        self.assertIn("os-0001", self.chamado.nome_arquivo_os)

    def test_recusa_arquivo_que_nao_e_pdf_nem_imagem(self):
        ruim = SimpleUploadedFile("os.docx", b"nao", content_type="application/msword")
        resposta = self.encerra(arquivo_os=ruim)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("arquivo_os", resposta.context["form"].errors)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AnexoDaOrdemDeServicoTests(BaseComChamado):
    """A folha assinada pode chegar depois — inclusive com a OS já encerrada."""

    def anexa(self, nome="os-0001.pdf", conteudo=b"%PDF-1.4 assinado"):
        return self.client.post(
            reverse("chamado_detalhe", args=[self.chamado.pk]),
            {
                "anexar": "1",
                "arquivo_os": SimpleUploadedFile(
                    nome, conteudo, content_type="application/pdf"
                ),
            },
        )

    def encerra_o_chamado(self):
        self.chamado.status = Chamado.Status.ENCERRADO
        self.chamado.realizado = "Trocada a fonte."
        self.chamado.encerrado_em = timezone.now()
        self.chamado.save()

    def test_anexa_depois_do_encerramento(self):
        self.encerra_o_chamado()
        self.assertEqual(self.anexa().status_code, 302)
        self.chamado.refresh_from_db()
        self.assertIn("os-0001", self.chamado.nome_arquivo_os)
        self.assertTrue(self.chamado.encerrado)   # continua encerrado

    def test_anexar_nao_encerra_um_chamado_aberto(self):
        self.anexa()
        self.chamado.refresh_from_db()
        self.assertTrue(self.chamado.arquivo_os)
        self.assertFalse(self.chamado.encerrado)

    def test_anexar_sem_escolher_arquivo_da_erro(self):
        resposta = self.client.post(
            reverse("chamado_detalhe", args=[self.chamado.pk]), {"anexar": "1"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("arquivo_os", resposta.context["anexo_form"].errors)

    def test_o_arquivo_anexado_abre_pelo_django(self):
        self.anexa()
        resposta = self.client.get(reverse("chamado_arquivo", args=[self.chamado.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/pdf")

    def test_sem_anexo_o_link_do_arquivo_da_404(self):
        resposta = self.client.get(reverse("chamado_arquivo", args=[self.chamado.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_quem_nao_esta_logado_nao_abre_o_comprovante(self):
        self.anexa()
        self.client.logout()
        resposta = self.client.get(reverse("chamado_arquivo", args=[self.chamado.pk]))
        self.assertEqual(resposta.status_code, 302)


class ValorNaoNegativoTests(TestCase):
    """Zero é um valor válido (equipamento cedido sem cobrança) — só
    negativo é barrado, nos 5 campos de valor monetário do sistema."""

    def test_valor_compra_do_equipamento(self):
        equipamento = Equipamento(
            marca="DELL", modelo="OPTIPLEX", numero_patrimonio="5001",
            valor_compra=Decimal("-1"),
        )
        with self.assertRaises(ValidationError):
            equipamento.full_clean()
        equipamento.valor_compra = Decimal("0")
        equipamento.full_clean()

    def test_custo_da_manutencao(self):
        equipamento = Equipamento.objects.create(
            marca="DELL", modelo="OPTIPLEX", numero_patrimonio="5002",
        )
        manutencao = Manutencao(
            equipamento=equipamento, descricao="Troca de peça",
            custo=Decimal("-1"),
        )
        with self.assertRaises(ValidationError):
            manutencao.full_clean()
        manutencao.custo = Decimal("0")
        manutencao.full_clean()

    def test_valor_da_locacao(self):
        equipamento = Equipamento.objects.create(
            marca="DELL", modelo="OPTIPLEX", numero_patrimonio="5003",
        )
        cliente = Cliente.objects.create(nome="CLIENTE X")
        locacao = Locacao(
            equipamento=equipamento, cliente=cliente, valor=Decimal("-1"),
            data_inicio="2026-08-01",
        )
        with self.assertRaises(ValidationError):
            locacao.full_clean()
        locacao.valor = Decimal("0")
        locacao.full_clean()

    def test_valor_do_contrato(self):
        contrato = Contrato(numero="1", valor=Decimal("-1"))
        with self.assertRaises(ValidationError):
            contrato.full_clean()
        contrato.valor = Decimal("0")
        contrato.full_clean()

    def test_valor_do_aditivo(self):
        contrato = Contrato.objects.create(numero="1")
        aditivo = Aditivo(
            contrato=contrato, numero=1, descricao="x", valor=Decimal("-1"),
        )
        with self.assertRaises(ValidationError):
            aditivo.full_clean()
        aditivo.valor = Decimal("0")
        aditivo.full_clean()


class ValorDoAditivoPorMaquinaTests(BaseLogada):
    """O valor de cada máquina marcada no aditivo vem de um campo próprio
    (lido direto do POST, fora do ModelForm) — zero é aceito (equipamento
    cedido sem cobrança), só negativo é recusado."""

    def setUp(self):
        super().setUp()
        self.cliente = Cliente.objects.create(nome="RODOSERGIPE")
        self.contrato = Contrato.objects.create(
            numero="10", cliente=self.cliente, data_contrato="2026-08-01"
        )
        self.maquina = Equipamento.objects.get(numero_patrimonio="1001")

    def enviar(self, valor):
        return self.client.post(
            reverse("aditivo_novo", args=[self.contrato.pk]),
            {
                "tipo": Aditivo.Tipo.ADICAO, "descricao": "", "valor": "",
                "data": "2026-09-01", "observacoes": "",
                "equipamentos": [self.maquina.pk],
                f"valor_equip_{self.maquina.pk}": valor,
            },
        )

    def test_aceita_maquina_marcada_com_valor_zero(self):
        resposta = self.enviar("0")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            Locacao.objects.get(equipamento=self.maquina).valor, Decimal("0")
        )

    def test_recusa_valor_negativo(self):
        resposta = self.enviar("-50")
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Locacao.objects.filter(equipamento=self.maquina).exists())


class ValorDeLocacaoEmLoteTests(BaseLogada):
    """Aplicar um mesmo valor a várias máquinas do contrato de uma vez."""

    def setUp(self):
        super().setUp()
        self.cliente = Cliente.objects.create(nome="RODOVIÁRIO")
        self.contrato = Contrato.objects.create(numero="77", cliente=self.cliente)
        self.outro_contrato = Contrato.objects.create(
            numero="88", cliente=self.cliente
        )
        self.m1 = Equipamento.objects.get(numero_patrimonio="1001")
        self.m2 = Equipamento.objects.get(numero_patrimonio="1002")
        self.m3 = Equipamento.objects.get(numero_patrimonio="1003")
        self.l1 = self.loca(self.m1, self.contrato, "100.00")
        self.l2 = self.loca(self.m2, self.contrato, "150.00")
        self.l3 = self.loca(self.m3, self.outro_contrato, "999.00")

    def loca(self, maquina, contrato, valor, ativa=True):
        return Locacao.objects.create(
            equipamento=maquina, cliente=self.cliente, contrato=contrato,
            valor=valor, data_inicio="2026-08-05", ativa=ativa,
        )

    def aplica(self, ids, valor="250.00", contrato=None):
        return self.client.post(
            reverse("locacao_valor_em_lote",
                    args=[(contrato or self.contrato).pk]),
            {"valor": valor, "locacoes": ids},
        )

    def test_aplica_o_mesmo_valor_nas_marcadas(self):
        resposta = self.aplica([self.l1.pk, self.l2.pk])
        self.assertEqual(resposta.status_code, 302)
        self.l1.refresh_from_db(); self.l2.refresh_from_db()
        self.assertEqual(str(self.l1.valor), "250.00")
        self.assertEqual(str(self.l2.valor), "250.00")

    def test_nao_mexe_em_quem_nao_foi_marcado(self):
        self.aplica([self.l1.pk])
        self.l2.refresh_from_db()
        self.assertEqual(str(self.l2.valor), "150.00")

    def test_nao_alcanca_locacao_de_outro_contrato(self):
        """Mesmo mandando o id na mão, a locação do contrato 88 não muda."""
        self.aplica([self.l1.pk, self.l3.pk])
        self.l3.refresh_from_db()
        self.assertEqual(str(self.l3.valor), "999.00")

    def test_nao_altera_locacao_encerrada(self):
        self.l2.ativa = False
        self.l2.save(update_fields=["ativa"])
        self.aplica([self.l1.pk, self.l2.pk])
        self.l2.refresh_from_db()
        self.assertEqual(str(self.l2.valor), "150.00")

    def test_sem_marcar_nenhuma_avisa_e_nao_muda_nada(self):
        self.aplica([])
        self.l1.refresh_from_db()
        self.assertEqual(str(self.l1.valor), "100.00")

    def test_valor_zero_e_aceito(self):
        """Máquina cedida sem cobrança — zero é um valor válido, só negativo não é."""
        resposta = self.aplica([self.l1.pk], valor="0")
        self.assertEqual(resposta.status_code, 302)
        self.l1.refresh_from_db()
        self.assertEqual(str(self.l1.valor), "0.00")

    def test_valor_negativo_e_recusado(self):
        self.aplica([self.l1.pk], valor="-10")
        self.l1.refresh_from_db()
        self.assertEqual(str(self.l1.valor), "100.00")

    def test_valor_vazio_e_recusado(self):
        self.aplica([self.l1.pk], valor="")
        self.l1.refresh_from_db()
        self.assertEqual(str(self.l1.valor), "100.00")

    def test_cada_alteracao_vira_linha_no_historico(self):
        self.aplica([self.l1.pk, self.l2.pk])
        historico = Movimentacao.objects.filter(equipamento=self.m1)
        self.assertEqual(historico.count(), 1)
        texto = historico.first().descricao
        self.assertIn("100,00", texto)
        self.assertIn("250,00", texto)
        self.assertIn("77", texto)

    def test_quem_ja_estava_no_valor_nao_gera_historico(self):
        self.aplica([self.l1.pk, self.l2.pk], valor="100.00")
        self.assertEqual(
            Movimentacao.objects.filter(equipamento=self.m1).count(), 0
        )
        self.l2.refresh_from_db()
        self.assertEqual(str(self.l2.valor), "100.00")

    def test_get_nao_altera_nada(self):
        self.client.get(reverse("locacao_valor_em_lote", args=[self.contrato.pk]))
        self.l1.refresh_from_db()
        self.assertEqual(str(self.l1.valor), "100.00")

    def test_a_tela_do_contrato_oferece_marcar_e_aplicar(self):
        html = self.client.get(
            reverse("contrato_detalhe", args=[self.contrato.pk])
        ).content.decode()
        self.assertIn('name="locacoes"', html)
        self.assertIn("marcar-todas", html)
        self.assertIn("Aplicar às", html)

    def test_sem_permissao_de_alterar_a_tela_nao_mostra_o_lote(self):
        sem_poder = get_user_model().objects.create_user(
            "recepcao", "r@exemplo.com", "senha-de-teste"
        )
        self.client.force_login(sem_poder)
        html = self.client.get(
            reverse("contrato_detalhe", args=[self.contrato.pk])
        ).content.decode()
        self.assertNotIn('name="locacoes"', html)

    def test_sem_permissao_o_post_e_barrado(self):
        sem_poder = get_user_model().objects.create_user(
            "recepcao2", "r2@exemplo.com", "senha-de-teste"
        )
        self.client.force_login(sem_poder)
        resposta = self.aplica([self.l1.pk])
        self.assertEqual(resposta.status_code, 403)
        self.l1.refresh_from_db()
        self.assertEqual(str(self.l1.valor), "100.00")
