"""Testes das telas de Produto (painel de produtos + cadastro com ficha técnica).

Rodam num banco de dados temporário — o db.sqlite3 de verdade não é tocado.
Para rodar:  python manage.py test inventario
"""

import importlib
import json

from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from .models import Cliente, Contrato, Equipamento, Locacao, Produto

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
