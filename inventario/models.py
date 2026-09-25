from datetime import timedelta

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

# Zero é um valor válido (equipamento cedido sem cobrança) — só negativo é
# rejeitado. Usado nos campos de valor monetário do sistema.
validar_nao_negativo = MinValueValidator(0, message="Não pode ser negativo.")


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
        "INF", max_length=80, unique=True,
        help_text="Número da etiqueta INF colada no equipamento.",
    )

    # Ficha técnica — só aparece para produtos com pede_configuracao=True
    # (Desktop e Notebook). Fica em branco para os demais.
    processador = models.CharField("Processador", max_length=120, blank=True)
    memoria_ram = models.CharField("Memória RAM", max_length=60, blank=True)
    armazenamento = models.CharField("Armazenamento (SSD/HD)", max_length=60, blank=True)

    # Controle patrimonial / compra
    valor_compra = models.DecimalField(
        "Valor pago na compra", max_digits=12, decimal_places=2,
        null=True, blank=True, validators=[validar_nao_negativo],
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
        return f"{self.marca} {self.modelo} (INF-{self.numero_patrimonio})"

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
        "Custo", max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[validar_nao_negativo],
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
    aditivo = models.ForeignKey(
        "Aditivo", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="locacoes", verbose_name="Aditivo",
        help_text="Aditivo que incluiu esta máquina no contrato, quando veio por um.",
    )
    valor = models.DecimalField(
        "Valor da locação", max_digits=12, decimal_places=2,
        validators=[validar_nao_negativo],
    )
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
    """Contrato (feito no Word e salvo em PDF) anexado ao sistema.

    Todo contrato tem vigência de 1 ano a partir de `data_contrato`, com
    renovação automática se ninguém conversar sobre isso até lá — não existe
    uma data de término real gravada no banco. O aviso de renovação avisa
    que a data de aniversário está chegando, não que o contrato "vai
    vencer": nada quebra sozinho se ninguém fizer nada.
    """

    # Quantos dias antes do aniversário o contrato já aparece como "perto de
    # renovar" na listagem.
    DIAS_ATE_RENOVACAO = 15

    numero = models.CharField("Número do contrato", max_length=50, db_index=True)
    titulo = models.CharField("Título / objeto", max_length=200, blank=True)
    cliente = models.ForeignKey(
        Cliente, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="contratos", verbose_name="Cliente",
    )
    data_contrato = models.DateField("Data do contrato", default=timezone.now)
    valor = models.DecimalField(
        "Valor", max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[validar_nao_negativo],
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
        # Áreas restritas do sistema. Quem concede é o Analista
        # (settings.USUARIO_ANALISTA), na tela "Usuários e permissões".
        permissions = [
            ("ver_contratos", "Pode ver a aba de Contratos"),
            ("ver_pdfs", "Pode abrir os PDFs anexados"),
        ]

    def __str__(self):
        if self.titulo:
            return f"Contrato {self.numero} — {self.titulo}"
        return f"Contrato {self.numero}"

    @property
    def nome_arquivo(self):
        import os
        return os.path.basename(self.arquivo.name) if self.arquivo else ""

    @property
    def maquinas_ativas(self):
        """Quantas máquinas o contrato tem **hoje**.

        Locação encerrada (máquina devolvida) continua no histórico do
        contrato, mas não entra nesta conta — é ela que aparece nas telas.
        """
        return self.locacoes.filter(ativa=True).count()

    @property
    def proxima_renovacao(self):
        """Próxima data de aniversário do contrato (1 ano de vigência).

        Sempre no futuro (hoje inclusive) — soma quantos anos forem
        necessários a partir de `data_contrato` até passar de hoje. Calculado
        na hora, não salvo: não existe "data de término" gravada no banco.
        """
        if not self.data_contrato:
            return None
        hoje = timezone.now().date()
        aniversario = self.data_contrato
        while aniversario < hoje:
            try:
                aniversario = aniversario.replace(year=aniversario.year + 1)
            except ValueError:
                # 29/02 num ano não bissexto: cai pro 1º de março.
                aniversario = aniversario.replace(
                    month=3, day=1, year=aniversario.year
                )
        return aniversario

    @property
    def dias_ate_renovacao(self):
        proxima = self.proxima_renovacao
        if proxima is None:
            return None
        return (proxima - timezone.now().date()).days

    @property
    def renovacao_proxima(self):
        """True quando a renovação automática está a poucos dias de acontecer."""
        dias = self.dias_ate_renovacao
        return dias is not None and dias <= self.DIAS_ATE_RENOVACAO


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
        help_text='Ex.: "Notebook Lenovo (INF-8974)", "1 máquina removida"...',
    )
    valor = models.DecimalField(
        "Valor do equipamento", max_digits=12, decimal_places=2,
        null=True, blank=True, validators=[validar_nao_negativo],
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


def formata_duracao(delta):
    """Transforma uma duração em algo legível: "2h 15min", "8min", "3d 4h"."""
    if delta is None:
        return "—"
    total = int(delta.total_seconds())
    if total < 60:
        return "menos de 1min"
    dias, resto = divmod(total, 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60
    if dias:
        return f"{dias}d {horas}h"
    if horas:
        return f"{horas}h {minutos:02d}min"
    return f"{minutos}min"


class Chamado(models.Model):
    """Chamado aberto na recepção e atendido pela área técnica.

    A **Ordem de Serviço** é a própria ficha do chamado: o que a recepção
    preenche na abertura (máquina, o que fazer, técnico designado) mais o que
    o técnico registra no encerramento (o que foi feito). O nº da OS é o nº
    do chamado.

    As duas pontas do tempo são gravadas pelo sistema, não digitadas:
    `aberto_em` na hora que a recepção salva e `encerrado_em` na hora que o
    técnico encerra. É disso que sai o tempo de cada atendimento no histórico
    do gerente técnico.
    """

    class Status(models.TextChoices):
        ABERTO = "ABERTO", "Aberto"
        ENCERRADO = "ENCERRADO", "Encerrado"

    class Prioridade(models.TextChoices):
        URGENTE = "URGENTE", "Urgente"
        NORMAL = "NORMAL", "Normal"
        LEVE = "LEVE", "Leve"

    # Chamado que passa disto sem encerrar vira alerta de sirene no painel da
    # área técnica — de 5 em 5 minutos, até alguém encerrar.
    HORAS_ATE_ATRASO = 24

    # Obrigatório no formulário de abertura (é o primeiro campo que a recepção
    # escolhe), mas aceita vazio no banco: existem chamados antigos e máquinas
    # sem locação, e travar isso quebraria o histórico já gravado.
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, null=True, blank=True,
        related_name="chamados", verbose_name="Cliente",
    )
    equipamento = models.ForeignKey(
        Equipamento, on_delete=models.CASCADE,
        related_name="chamados", verbose_name="Máquina",
    )
    descricao = models.TextField(
        "O que deve ser feito",
        help_text="Descreva o problema ou o serviço pedido.",
    )
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="chamados_designados", verbose_name="Técnico designado",
    )
    solicitante = models.CharField(
        "Quem pediu", max_length=120, blank=True,
        help_text="Nome de quem procurou a recepção (opcional).",
    )

    prioridade = models.CharField(
        "Urgência", max_length=10, choices=Prioridade.choices,
        default=Prioridade.NORMAL,
        help_text="Urgente = parou o trabalho · Normal = do dia · Leve = pode esperar.",
    )
    status = models.CharField(
        "Status", max_length=10, choices=Status.choices, default=Status.ABERTO
    )

    aberto_em = models.DateTimeField("Aberto em", auto_now_add=True)
    aberto_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="chamados_abertos", verbose_name="Aberto por",
    )

    realizado = models.TextField("O que foi realizado", blank=True)

    # --- O que vem da OS física preenchida pelo técnico no atendimento ---
    houve_troca_peca = models.BooleanField("Houve troca de peça?", default=False)
    peca_substituida = models.CharField(
        "Peça substituída", max_length=200, blank=True,
        help_text='Ex.: "Fonte 500W", "Toner preto", "SSD 240 GB".',
    )
    observacoes = models.TextField("Observações do atendimento", blank=True)

    # A folha assinada, digitalizada. É o comprovante do atendimento: fica
    # guardada e pode ser anexada depois do encerramento, se o scanner só
    # estiver disponível mais tarde.
    arquivo_os = models.FileField(
        "OS digitalizada (PDF ou imagem)", upload_to="ordens_servico/%Y/",
        blank=True,
    )

    encerrado_em = models.DateTimeField("Encerrado em", null=True, blank=True)
    encerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="chamados_encerrados", verbose_name="Encerrado por",
    )

    class Meta:
        verbose_name = "Chamado"
        verbose_name_plural = "Chamados"
        ordering = ["-aberto_em", "-id"]

    def __str__(self):
        return f"OS {self.numero_os} — {self.equipamento}"

    @property
    def numero_os(self):
        """Nº da Ordem de Serviço, com zeros à esquerda (OS 0042)."""
        return f"{self.pk:04d}" if self.pk else "—"

    @property
    def encerrado(self):
        return self.status == self.Status.ENCERRADO

    @property
    def atrasado(self):
        """Aberto há mais de 24h e ainda sem encerramento.

        É o que dispara a sirene do painel e deixa o cartão piscando: numa
        TV transmitindo o painel o dia inteiro, é o que faz alguém olhar.
        """
        if self.encerrado or not self.aberto_em:
            return False
        return timezone.now() - self.aberto_em >= timedelta(
            hours=self.HORAS_ATE_ATRASO
        )

    @property
    def nome_arquivo_os(self):
        import os
        return os.path.basename(self.arquivo_os.name) if self.arquivo_os else ""

    @property
    def peca_texto(self):
        """O que mostrar na linha "troca de peça" das telas."""
        if not self.houve_troca_peca:
            return "Não houve troca de peça"
        return self.peca_substituida or "Sim — peça não especificada"

    @property
    def alerta(self):
        """Cores e o rótulo do alerta de urgência, para as telas usarem.

        `ordem` serve para o painel da área técnica colocar os urgentes na
        frente (1 vem antes de 3).
        """
        tabela = {
            self.Prioridade.URGENTE: {
                "cor": "#DC2626", "texto": "#FFFFFF", "icone": "🔴",
                "rotulo": "Urgente", "ordem": 1,
            },
            self.Prioridade.NORMAL: {
                "cor": "#EAB308", "texto": "#1F2937", "icone": "🟡",
                "rotulo": "Normal", "ordem": 2,
            },
            self.Prioridade.LEVE: {
                "cor": "#16A34A", "texto": "#FFFFFF", "icone": "🟢",
                "rotulo": "Leve", "ordem": 3,
            },
        }
        return tabela.get(self.prioridade, tabela[self.Prioridade.NORMAL])

    @property
    def urgente(self):
        return self.prioridade == self.Prioridade.URGENTE

    @property
    def duracao(self):
        """Tempo da abertura até o encerramento. None enquanto está aberto."""
        if not self.encerrado_em or not self.aberto_em:
            return None
        return self.encerrado_em - self.aberto_em

    @property
    def duracao_texto(self):
        return formata_duracao(self.duracao)

    @property
    def tempo_aberto(self):
        """Há quanto tempo o chamado está aberto (para o painel da área técnica)."""
        if self.encerrado or not self.aberto_em:
            return None
        return timezone.now() - self.aberto_em

    @property
    def tempo_aberto_texto(self):
        return formata_duracao(self.tempo_aberto)
