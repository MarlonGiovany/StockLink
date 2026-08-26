from django.conf import settings
from django.db import models
from django.utils import timezone


class Fornecedor(models.Model):
    """Fornecedor de quem a empresa compra equipamentos."""

    nome = models.CharField("Nome", max_length=120)
    cnpj = models.CharField("CNPJ", max_length=20, blank=True)
    telefone = models.CharField("Telefone", max_length=30, blank=True)
    email = models.EmailField("E-mail", blank=True)
    observacoes = models.TextField("Observações", blank=True)

    class Meta:
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Cliente(models.Model):
    """Cliente para quem a empresa loca equipamentos."""

    nome = models.CharField("Nome / Razão social", max_length=120)
    documento = models.CharField("CPF/CNPJ", max_length=20, blank=True)
    telefone = models.CharField("Telefone", max_length=30, blank=True)
    email = models.EmailField("E-mail", blank=True)
    endereco = models.CharField("Endereço", max_length=200, blank=True)
    observacoes = models.TextField("Observações", blank=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Produto(models.Model):
    """Tipo de produto com que a empresa trabalha (Desktop, Impressora...).

    Serve para agrupar os equipamentos. A lista começa com os produtos que a
    INFORLINK já trabalha, e cresce pelo botão "Adicionar novo produto" na
    tela de cadastro de equipamento.
    """

    nome = models.CharField("Nome do produto", max_length=80, unique=True)
    ordem = models.PositiveIntegerField(
        "Ordem de exibição", default=100,
        help_text="Menor aparece primeiro. Produtos novos entram no fim.",
    )
    pede_configuracao = models.BooleanField(
        "Pede configuração (processador / RAM / armazenamento)", default=False,
        help_text="Marque para produtos como Desktop e Notebook, que precisam "
                  "desses três campos a mais no cadastro.",
    )
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome


class Equipamento(models.Model):
    """Item de patrimônio da empresa."""

    class Status(models.TextChoices):
        DISPONIVEL = "DISPONIVEL", "Disponível"
        LOCADO = "LOCADO", "Locado"
        MANUTENCAO = "MANUTENCAO", "Em manutenção"
        BAIXADO = "BAIXADO", "Baixado / Descartado"

    # Identificação
    produto = models.ForeignKey(
        Produto, on_delete=models.PROTECT, null=True, blank=True,
        related_name="equipamentos", verbose_name="Produto",
    )
    marca = models.CharField("Marca", max_length=80)
    modelo = models.CharField("Modelo", max_length=80)
    numero_serie = models.CharField("Número de série", max_length=80, blank=True)
    numero_patrimonio = models.CharField(
        "Número de patrimônio", max_length=80, unique=True
    )

    # Ficha técnica — só aparece para produtos com pede_configuracao=True
    # (Desktop e Notebook). Fica em branco para os demais.
    processador = models.CharField("Processador", max_length=120, blank=True)
    memoria_ram = models.CharField("Memória RAM", max_length=60, blank=True)
    armazenamento = models.CharField("Armazenamento (SSD/HD)", max_length=60, blank=True)

    # Controle patrimonial / compra
    valor_compra = models.DecimalField(
        "Valor pago na compra", max_digits=12, decimal_places=2,
        null=True, blank=True,
    )
    data_aquisicao = models.DateField("Data de aquisição", null=True, blank=True)
    fornecedor = models.ForeignKey(
        Fornecedor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="equipamentos", verbose_name="Fornecedor",
    )

    # Situação atual
    local = models.CharField("Localização atual", max_length=120, blank=True)
    status = models.CharField(
        "Status", max_length=15, choices=Status.choices, default=Status.DISPONIVEL
    )
    observacoes = models.TextField("Observações", blank=True)

    criado_em = models.DateTimeField("Cadastrado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Equipamento"
        verbose_name_plural = "Equipamentos"
        ordering = ["marca", "modelo"]

    def __str__(self):
        return f"{self.marca} {self.modelo} (Pat. {self.numero_patrimonio})"

    @property
    def locacao_ativa(self):
        return self.locacoes.filter(ativa=True).first()

    @property
    def nivel_problema(self):
        """Classifica o equipamento pela quantidade de manutenções já feitas.
        Quanto mais manutenções, mais problemático o equipamento.

        🟢 até 2 manutenções · 🟡 3ª · 🟠 4ª · 🔴 5ª ou mais
        """
        n = self.manutencoes.count()
        if n <= 2:
            cor, rotulo, nivel = "#16A34A", "Tranquilo", 1      # verde
        elif n == 3:
            cor, rotulo, nivel = "#EAB308", "Atenção", 2        # amarelo
        elif n == 4:
            cor, rotulo, nivel = "#F97316", "Alerta", 3         # laranja
        else:
            cor, rotulo, nivel = "#DC2626", "Crítico", 4        # vermelho
        return {"qtd": n, "cor": cor, "rotulo": rotulo, "nivel": nivel}


class Manutencao(models.Model):
    """Intervenção técnica realizada em um equipamento."""

    equipamento = models.ForeignKey(
        Equipamento, on_delete=models.CASCADE,
        related_name="manutencoes", verbose_name="Equipamento",
    )
    data = models.DateField("Data", default=timezone.now)
    descricao = models.TextField("Descrição do serviço")
    custo = models.DecimalField(
        "Custo", max_digits=12, decimal_places=2, null=True, blank=True
    )
    tecnico = models.CharField("Técnico responsável", max_length=120, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Registrado por",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Manutenção"
        verbose_name_plural = "Manutenções"
        ordering = ["-data", "-id"]

    def __str__(self):
        return f"Manutenção {self.data} - {self.equipamento}"


class Locacao(models.Model):
    """Contrato de locação de um equipamento para um cliente."""

    equipamento = models.ForeignKey(
        Equipamento, on_delete=models.CASCADE,
        related_name="locacoes", verbose_name="Equipamento",
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT,
        related_name="locacoes", verbose_name="Cliente",
    )
    contrato = models.ForeignKey(
        "Contrato", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="locacoes", verbose_name="Contrato",
    )
    valor = models.DecimalField("Valor da locação", max_digits=12, decimal_places=2)
    data_inicio = models.DateField("Início do contrato")
    data_fim = models.DateField("Término do contrato", null=True, blank=True)
    ativa = models.BooleanField("Locação ativa", default=True)
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Locação"
        verbose_name_plural = "Locações"
        ordering = ["-data_inicio", "-id"]

    def __str__(self):
        return f"{self.equipamento} → {self.cliente}"


class Contrato(models.Model):
    """Contrato (feito no Word e salvo em PDF) anexado ao sistema."""

    numero = models.CharField("Número do contrato", max_length=50, db_index=True)
    titulo = models.CharField("Título / objeto", max_length=200, blank=True)
    cliente = models.ForeignKey(
        Cliente, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="contratos", verbose_name="Cliente",
    )
    data_contrato = models.DateField("Data do contrato", default=timezone.now)
    valor = models.DecimalField(
        "Valor", max_digits=12, decimal_places=2, null=True, blank=True
    )
    arquivo = models.FileField("Arquivo (PDF)", upload_to="contratos/%Y/", blank=True)
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField("Anexado em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Anexado por",
    )

    class Meta:
        verbose_name = "Contrato"
        verbose_name_plural = "Contratos"
        ordering = ["-data_contrato", "-id"]

    def __str__(self):
        if self.titulo:
            return f"Contrato {self.numero} — {self.titulo}"
        return f"Contrato {self.numero}"

    @property
    def nome_arquivo(self):
        import os
        return os.path.basename(self.arquivo.name) if self.arquivo else ""


class Aditivo(models.Model):
    """Registro de um aditivo (alteração) feito dentro de um contrato.

    Serve apenas como histórico: cada aditivo é numerado em sequência
    (1, 2, 3...) e marca se foi uma adição ou remoção de equipamento, com
    a descrição, a data e o preço do equipamento. NÃO altera o valor do
    contrato — esse é manual.
    """

    class Tipo(models.TextChoices):
        ADICAO = "ADICAO", "Adição"
        REMOCAO = "REMOCAO", "Remoção"

    contrato = models.ForeignKey(
        Contrato, on_delete=models.CASCADE,
        related_name="aditivos", verbose_name="Contrato",
    )
    numero = models.PositiveIntegerField("Nº do aditivo")
    tipo = models.CharField(
        "Tipo de alteração", max_length=10, choices=Tipo.choices,
        default=Tipo.ADICAO,
    )
    descricao = models.CharField(
        "Equipamento / descrição", max_length=200,
        help_text='Ex.: "Notebook Lenovo (Pat. 8974)", "1 máquina removida"...',
    )
    valor = models.DecimalField(
        "Valor do equipamento", max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Preço do equipamento desta alteração. Apenas registro — não muda o valor do contrato.",
    )
    data = models.DateField("Data do aditivo", default=timezone.now)
    arquivo = models.FileField(
        "PDF do aditivo (opcional)", upload_to="aditivos/%Y/", blank=True
    )
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Registrado por",
    )

    class Meta:
        verbose_name = "Aditivo"
        verbose_name_plural = "Aditivos"
        ordering = ["contrato", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["contrato", "numero"], name="aditivo_numero_unico_por_contrato"
            )
        ]

    def __str__(self):
        return f"Aditivo {self.numero} — {self.contrato.numero}"


class Movimentacao(models.Model):
    """Registro imutável (append-only) de tudo que acontece com um equipamento."""

    class Tipo(models.TextChoices):
        CADASTRO = "CADASTRO", "Cadastro"
        EDICAO = "EDICAO", "Edição"
        LOCAL = "LOCAL", "Mudança de localização"
        STATUS = "STATUS", "Mudança de status"
        MANUTENCAO = "MANUTENCAO", "Manutenção"
        LOCACAO = "LOCACAO", "Locação"
        DEVOLUCAO = "DEVOLUCAO", "Devolução"
        BAIXA = "BAIXA", "Baixa"

    equipamento = models.ForeignKey(
        Equipamento, on_delete=models.CASCADE,
        related_name="movimentacoes", verbose_name="Equipamento",
    )
    tipo = models.CharField("Tipo", max_length=15, choices=Tipo.choices)
    descricao = models.CharField("Descrição", max_length=255)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Usuário",
    )
    data = models.DateTimeField("Data/hora", auto_now_add=True)

    class Meta:
        verbose_name = "Movimentação"
        verbose_name_plural = "Movimentações"
        ordering = ["-data", "-id"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.equipamento} ({self.data:%d/%m/%Y %H:%M})"
