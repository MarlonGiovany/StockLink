import re
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import (
    Aditivo,
    Chamado,
    Cliente,
    Contrato,
    Equipamento,
    Fornecedor,
    Locacao,
    Manutencao,
    Produto,
)


def _apenas_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def _formata_cpf(digitos):
    return f"{digitos[0:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:11]}"


def _formata_cnpj(digitos):
    return f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:14]}"


def _formata_telefone(digitos):
    if len(digitos) == 11:
        return f"({digitos[0:2]}) {digitos[2:7]}-{digitos[7:11]}"
    return f"({digitos[0:2]}) {digitos[2:6]}-{digitos[6:10]}"


class _ArquivoAtual:
    """O arquivo já anexado, como o widget de upload o mostra.

    Mesmo texto de sempre (o caminho do arquivo); só o endereço do link muda.
    """

    def __init__(self, arquivo, url):
        self.arquivo = arquivo
        self.url = url

    def __str__(self):
        return str(self.arquivo)


class LinkProtegidoMixin:
    """Faz o "Atualmente: arquivo.pdf" do campo de upload abrir pela view
    que confere a permissão, e não por /media/.

    O Django monta esse link com o endereço público do arquivo (/media/...),
    que o servidor não entrega mais — a pasta media só sai pelo Django, depois
    da checagem de login e de permissão. Sem a troca o link dava 404; antes
    de a pasta ser fechada, ele abria o PDF para qualquer um.

    Quem define o endereço é `protege_arquivo()`, porque ele depende do
    registro que está sendo editado.
    """

    url_protegida = None

    def get_context(self, name, value, attrs):
        contexto = super().get_context(name, value, attrs)
        if contexto["widget"]["is_initial"] and self.url_protegida:
            contexto["widget"]["value"] = _ArquivoAtual(value, self.url_protegida)
        return contexto


class ArquivoProtegidoInput(LinkProtegidoMixin, forms.ClearableFileInput):
    pass


def protege_arquivo(form, campo, rota):
    """Aponta o link do arquivo atual de `campo` para a view `rota`."""
    instancia = form.instance
    if campo in form.fields and instancia.pk and getattr(instancia, campo):
        form.fields[campo].widget.url_protegida = reverse(rota, args=[instancia.pk])


class BootstrapFormMixin:
    """Aplica classes do Bootstrap automaticamente a todos os campos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput,)):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class ProdutoForm(BootstrapFormMixin, forms.ModelForm):
    """Cadastro rápido de um produto novo — só o nome."""

    class Meta:
        model = Produto
        fields = ["nome"]
        widgets = {
            "nome": forms.TextInput(
                attrs={"placeholder": "Ex.: Projetor, Servidor, Nobreak...",
                       "autofocus": "autofocus"}
            ),
        }

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        if not nome:
            raise forms.ValidationError("Escreva o nome do produto.")
        # Evita "impressora" virar um produto separado de "Impressora"
        existente = Produto.objects.filter(nome__iexact=nome).first()
        if existente and existente.pk != self.instance.pk:
            raise forms.ValidationError(
                f'O produto "{existente.nome}" já existe na lista.'
            )
        return nome

    def save(self, commit=True):
        produto = super().save(commit=False)
        # Produto novo entra no fim da lista
        ultimo = Produto.objects.order_by("-ordem").first()
        produto.ordem = (ultimo.ordem + 10) if ultimo else 10
        if commit:
            produto.save()
        return produto


class EquipamentoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Equipamento
        fields = [
            "produto",
            "marca", "modelo", "numero_serie", "numero_patrimonio",
            "processador", "memoria_ram", "armazenamento",
            "valor_compra", "data_aquisicao", "fornecedor",
            "local", "status", "observacoes",
        ]
        widgets = {
            "data_aquisicao": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
            "processador": forms.TextInput(
                attrs={"placeholder": "Ex.: Intel Core i5-10500"}
            ),
            "memoria_ram": forms.TextInput(attrs={"placeholder": "Ex.: 8 GB DDR4"}),
            "armazenamento": forms.TextInput(attrs={"placeholder": "Ex.: SSD 256 GB"}),
        }

    # Campos que só aparecem quando o produto pede configuração
    CAMPOS_CONFIGURACAO = ["processador", "memoria_ram", "armazenamento"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["produto"].queryset = Produto.objects.filter(ativo=True)
        self.fields["produto"].required = True
        self.fields["produto"].empty_label = "— escolha o produto —"

    def clean(self):
        dados = super().clean()
        produto = dados.get("produto")
        # Se o produto não pede configuração, não guarda lixo nesses campos
        if produto and not produto.pede_configuracao:
            for campo in self.CAMPOS_CONFIGURACAO:
                dados[campo] = ""
        return dados


class ManutencaoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Manutencao
        fields = ["data", "descricao", "custo", "tecnico"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "descricao": forms.Textarea(attrs={"rows": 3}),
        }


class ContratoSelect(forms.Select):
    """Select de contratos que marca cada opção com o cliente dono.

    O `data-cliente` é o que permite a tela mostrar só os contratos do
    cliente escolhido na locação.
    """

    def create_option(self, name, value, label, selected, index,
                      subindex=None, attrs=None):
        opcao = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        contrato = getattr(value, "instance", None)
        if contrato is not None:
            opcao["attrs"]["data-cliente"] = contrato.cliente_id or ""
        return opcao


class ContratoChoiceField(forms.ModelChoiceField):
    """Mostra o contrato de um jeito reconhecível: número, cliente e data."""

    widget = ContratoSelect

    def label_from_instance(self, obj):
        partes = [f"Nº {obj.numero}"]
        if obj.cliente:
            partes.append(str(obj.cliente))
        if obj.data_contrato:
            partes.append(obj.data_contrato.strftime("%d/%m/%Y"))
        return " · ".join(partes)


def contratos_disponiveis():
    return Contrato.objects.select_related("cliente").all()


class LocacaoForm(BootstrapFormMixin, forms.ModelForm):
    contrato = ContratoChoiceField(
        queryset=Contrato.objects.none(),
        required=False,
        label="Contrato",
        empty_label="— sem contrato por enquanto —",
        help_text="Escolha um contrato que já existe para este cliente. "
                  "Um mesmo contrato pode ter várias máquinas.",
    )

    class Meta:
        model = Locacao
        fields = [
            "cliente", "contrato", "valor",
            "data_inicio", "data_fim", "ativa", "observacoes",
        ]
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "data_fim": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contrato"].queryset = contratos_disponiveis()

    def clean(self):
        dados = super().clean()
        cliente = dados.get("cliente")
        contrato = dados.get("contrato")
        # Trava de segurança: não deixa pendurar a locação no contrato de outro cliente
        if contrato and cliente and contrato.cliente_id:
            if contrato.cliente_id != cliente.pk:
                self.add_error(
                    "contrato",
                    f'O contrato Nº {contrato.numero} é do cliente '
                    f'"{contrato.cliente}". Escolha um contrato de {cliente} '
                    f'ou deixe em branco para anexar depois.',
                )
        return dados


class ValorEmLoteForm(forms.Form):
    """O valor único que vai ser aplicado às máquinas marcadas.

    Num contrato é comum a frota inteira sair pelo mesmo preço; digitar
    máquina por máquina era o trabalho que a edição em lote tira.
    """

    valor = forms.DecimalField(
        label="Aplicar este valor", max_digits=12, decimal_places=2,
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={
            "class": "form-control", "step": "0.01", "min": "0",
            "placeholder": "Ex.: 250,00",
        }),
        error_messages={
            "required": "Digite o valor da locação.",
            "invalid": "Valor inválido — use números, ex.: 250.00",
            "min_value": "O valor da locação não pode ser negativo.",
        },
    )


class FornecedorForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = ["nome", "cnpj", "telefone", "email", "observacoes"]
        widgets = {
            "cnpj": forms.TextInput(attrs={
                "data-mascara": "cnpj",
                "inputmode": "numeric",
                "autocomplete": "off",
                "placeholder": "00.000.000/0000-00",
            }),
            "telefone": forms.TextInput(attrs={
                "data-mascara": "telefone",
                "inputmode": "numeric",
                "autocomplete": "off",
                "placeholder": "(00) 00000-0000",
            }),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_cnpj(self):
        valor = (self.cleaned_data.get("cnpj") or "").strip()
        if not valor:
            return valor
        digitos = _apenas_digitos(valor)
        if len(digitos) != 14:
            raise forms.ValidationError("Digite um CNPJ com 14 números.")
        return _formata_cnpj(digitos)

    def clean_telefone(self):
        valor = (self.cleaned_data.get("telefone") or "").strip()
        if not valor:
            return valor
        digitos = _apenas_digitos(valor)
        if len(digitos) not in (10, 11):
            raise forms.ValidationError(
                "Digite um telefone com DDD (10 ou 11 números)."
            )
        return _formata_telefone(digitos)


class ClienteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "documento", "telefone", "email", "endereco", "observacoes"]
        widgets = {
            "documento": forms.TextInput(attrs={
                "data-mascara": "documento",
                "inputmode": "numeric",
                "autocomplete": "off",
                "placeholder": "CPF ou CNPJ — só números",
            }),
            "telefone": forms.TextInput(attrs={
                "data-mascara": "telefone",
                "inputmode": "numeric",
                "autocomplete": "off",
                "placeholder": "(00) 00000-0000",
            }),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_documento(self):
        valor = (self.cleaned_data.get("documento") or "").strip()
        if not valor:
            return valor
        digitos = _apenas_digitos(valor)
        if len(digitos) == 11:
            return _formata_cpf(digitos)
        if len(digitos) == 14:
            return _formata_cnpj(digitos)
        raise forms.ValidationError(
            "Digite um CPF (11 números) ou um CNPJ (14 números)."
        )

    def clean_telefone(self):
        valor = (self.cleaned_data.get("telefone") or "").strip()
        if not valor:
            return valor
        digitos = _apenas_digitos(valor)
        if len(digitos) not in (10, 11):
            raise forms.ValidationError(
                "Digite um telefone com DDD (10 ou 11 números)."
            )
        return _formata_telefone(digitos)


class ContratoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Contrato
        fields = [
            "numero", "titulo", "cliente", "data_contrato",
            "valor", "arquivo", "observacoes",
        ]
        widgets = {
            "data_contrato": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
            "arquivo": ArquivoProtegidoInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        protege_arquivo(self, "arquivo", "contrato_pdf")

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get("arquivo")
        if arquivo and getattr(arquivo, "name", "") and not arquivo.name.lower().endswith(".pdf"):
            raise forms.ValidationError("O contrato precisa estar em PDF (.pdf).")
        return arquivo


class AditivoForm(BootstrapFormMixin, forms.ModelForm):
    """Registra o aditivo e, quando for Adição, já inclui as máquinas marcadas.

    `descricao` e `valor` continuam existindo para o registro manual de
    sempre (principalmente Remoção, que não passa por seleção de máquinas).
    Quando `equipamentos` vem marcado, os dois são preenchidos sozinhos: a
    descrição lista as máquinas, e o valor vira a **soma do valor real de
    cada uma** — cada máquina tem seu próprio campo de valor no template
    (`valor_equip_<id>`, lido direto do POST na view, não é campo deste
    form) porque o preço pode variar de máquina pra máquina dentro do
    mesmo aditivo; não faz sentido forçar todas ao mesmo valor.
    """

    equipamentos = forms.ModelMultipleChoiceField(
        queryset=Equipamento.objects.none(),
        required=False,
        label="Máquinas incluídas neste aditivo",
        widget=forms.CheckboxSelectMultiple,
        help_text="Só aparecem as máquinas com status Disponível — as demais já "
                  "estão locadas, em manutenção ou baixadas.",
    )

    class Meta:
        model = Aditivo
        fields = ["tipo", "descricao", "valor", "data", "arquivo", "observacoes"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["equipamentos"].queryset = (
            Equipamento.objects.filter(status=Equipamento.Status.DISPONIVEL)
            .select_related("produto")
            .order_by("numero_patrimonio")
        )
        # O mixin bootstrap marca todo campo fora de select/checkbox único como
        # "form-control"; aqui é uma lista de checkboxes, então corrige a classe.
        self.fields["equipamentos"].widget.attrs["class"] = "form-check-input"
        # Preenchidos automaticamente quando há máquinas marcadas (ver clean()).
        self.fields["descricao"].required = False
        self.fields["valor"].required = False

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get("arquivo")
        if arquivo and getattr(arquivo, "name", "") and not arquivo.name.lower().endswith(".pdf"):
            raise forms.ValidationError("O aditivo precisa estar em PDF (.pdf).")
        return arquivo

    def clean(self):
        dados = super().clean()
        equipamentos = dados.get("equipamentos")
        if not equipamentos and not dados.get("descricao"):
            self.add_error(
                "descricao",
                "Marque ao menos uma máquina disponível acima, ou descreva a "
                "alteração manualmente (é o caso de uma Remoção, por exemplo).",
            )
        return dados


class AditivoEdicaoForm(BootstrapFormMixin, forms.ModelForm):
    """Corrige um aditivo já registrado — só os dados do registro.

    Não mexe nas máquinas: incluir ou tirar máquina continua sendo pelo
    aditivo novo e pela exclusão do último aditivo, que cuidam das locações
    e do status de cada equipamento. O número também não muda, para não
    furar a sequência do contrato.

    Quando o aditivo incluiu máquinas, o tipo (Adição) e o valor (soma das
    máquinas) ficam travados: mudar só aqui deixaria o registro dizendo uma
    coisa e as locações outra. O valor de cada máquina se ajusta na ficha do
    contrato, em "valor em lote".
    """

    class Meta:
        model = Aditivo
        fields = ["tipo", "descricao", "valor", "data", "arquivo", "observacoes"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
            "arquivo": ArquivoProtegidoInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        protege_arquivo(self, "arquivo", "aditivo_pdf")
        if self.instance.pk and self.instance.locacoes.exists():
            for campo in ("tipo", "valor"):
                self.fields[campo].disabled = True
            self.fields["valor"].help_text = (
                "Soma do valor das máquinas deste aditivo. Para mudar, ajuste o "
                "valor das máquinas na ficha do contrato."
            )

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get("arquivo")
        if arquivo and getattr(arquivo, "name", "") and not arquivo.name.lower().endswith(".pdf"):
            raise forms.ValidationError("O aditivo precisa estar em PDF (.pdf).")
        return arquivo


class EquipamentoSelect(forms.Select):
    """Select de máquinas que marca cada opção com o cliente dono.

    O `data-cliente` é o que permite a tela mostrar só as máquinas do cliente
    escolhido — mesma ideia do select de contratos da locação.
    """

    def create_option(self, name, value, label, selected, index,
                      subindex=None, attrs=None):
        opcao = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        equipamento = getattr(value, "instance", None)
        if equipamento is not None:
            locacao = equipamento.locacao_ativa
            opcao["attrs"]["data-cliente"] = locacao.cliente_id if locacao else ""
        return opcao


class EquipamentoChoiceField(forms.ModelChoiceField):
    """Mostra a máquina do jeito que a recepção reconhece: INF + modelo."""

    widget = EquipamentoSelect

    def label_from_instance(self, obj):
        produto = f"{obj.produto} — " if obj.produto else ""
        return f"INF-{obj.numero_patrimonio} — {produto}{obj.marca} {obj.modelo}"


def maquinas_com_cliente():
    """As máquinas que estão locadas para algum cliente hoje.

    O chamado é sempre da máquina de um cliente, então a lista sai daqui:
    equipamento com locação **ativa**. Máquina sem locação não aparece.
    """
    return (
        Equipamento.objects
        .filter(locacoes__ativa=True)
        .select_related("produto")
        .distinct()
        .order_by("numero_patrimonio")
    )


class ChamadoAberturaForm(BootstrapFormMixin, forms.ModelForm):
    """O que a recepção preenche ao abrir o chamado.

    A ordem dos campos é a ordem de preenchimento: **primeiro o cliente**, e
    só então a máquina — a lista de máquinas mostra apenas as daquele cliente.
    A data e a hora de abertura não estão aqui de propósito: quem grava é o
    sistema, no momento em que o chamado é salvo.
    """

    equipamento = EquipamentoChoiceField(
        queryset=Equipamento.objects.none(),
        label="Máquina",
        empty_label="— escolha o cliente primeiro —",
    )

    class Meta:
        model = Chamado
        fields = [
            "cliente", "equipamento", "prioridade",
            "descricao", "tecnico", "solicitante",
        ]
        widgets = {
            "descricao": forms.Textarea(
                attrs={"rows": 4,
                       "placeholder": "Ex.: computador não liga; trocar toner..."}
            ),
            "solicitante": forms.TextInput(
                attrs={"placeholder": "Ex.: Maria, do faturamento"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Só clientes que têm ao menos uma máquina locada — escolher um cliente
        # sem máquina só levaria a uma lista vazia na linha de baixo.
        self.fields["cliente"].queryset = (
            Cliente.objects.filter(locacoes__ativa=True).distinct().order_by("nome")
        )
        self.fields["cliente"].required = True
        self.fields["cliente"].empty_label = "— escolha o cliente —"

        self.fields["equipamento"].queryset = maquinas_com_cliente()

        self.fields["tecnico"].queryset = (
            get_user_model().objects.filter(is_active=True).order_by("username")
        )
        self.fields["tecnico"].required = True
        self.fields["tecnico"].empty_label = "— escolha o técnico —"

    def clean(self):
        dados = super().clean()
        cliente = dados.get("cliente")
        equipamento = dados.get("equipamento")

        # Trava de segurança: a máquina precisa estar mesmo com aquele cliente,
        # senão dava para burlar a lista mexendo no HTML da página.
        if cliente and equipamento:
            locacao = equipamento.locacao_ativa
            if not locacao or locacao.cliente_id != cliente.pk:
                dono = locacao.cliente if locacao else None
                self.add_error(
                    "equipamento",
                    f"A máquina INF-{equipamento.numero_patrimonio} não está "
                    f"locada para {cliente}"
                    + (f" — ela está com {dono}." if dono else "."),
                )
        return dados


# Formatos aceitos na digitalização da OS: o scanner da recepção costuma
# entregar PDF, mas foto do celular resolve quando o scanner está ocupado.
EXTENSOES_OS = (".pdf", ".jpg", ".jpeg", ".png")


def _valida_arquivo_os(arquivo):
    if arquivo and getattr(arquivo, "name", ""):
        if not arquivo.name.lower().endswith(EXTENSOES_OS):
            raise forms.ValidationError(
                "A OS digitalizada precisa ser PDF, JPG ou PNG."
            )
    return arquivo


class ChamadoEncerramentoForm(BootstrapFormMixin, forms.ModelForm):
    """O que o técnico passa da OS física para o sistema ao encerrar.

    Os campos são os mesmos da folha impressa, na mesma ordem: o que foi
    feito, se trocou peça, qual peça, observações e a folha digitalizada.
    """

    class Meta:
        model = Chamado
        fields = [
            "realizado", "houve_troca_peca", "peca_substituida",
            "observacoes", "arquivo_os",
        ]
        widgets = {
            "realizado": forms.Textarea(
                attrs={"rows": 5,
                       "placeholder": "Descreva o que foi feito no atendimento."}
            ),
            "peca_substituida": forms.TextInput(
                attrs={"placeholder": "Ex.: Fonte 500W, Toner preto, SSD 240 GB"}
            ),
            "observacoes": forms.Textarea(
                attrs={"rows": 3,
                       "placeholder": "Outras observações pertinentes (opcional)."}
            ),
            "arquivo_os": ArquivoProtegidoInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        protege_arquivo(self, "arquivo_os", "chamado_arquivo")

    def clean_realizado(self):
        texto = (self.cleaned_data.get("realizado") or "").strip()
        if not texto:
            raise forms.ValidationError(
                "Escreva o que foi realizado antes de encerrar o chamado."
            )
        return texto

    def clean_arquivo_os(self):
        return _valida_arquivo_os(self.cleaned_data.get("arquivo_os"))

    def clean(self):
        dados = super().clean()
        # "Sim, trocou peça" sem dizer qual peça não serve de comprovante —
        # é justamente essa informação que a OS física pede.
        if dados.get("houve_troca_peca") and not (dados.get("peca_substituida") or "").strip():
            self.add_error(
                "peca_substituida",
                "Diga qual peça foi substituída.",
            )
        # Peça escrita com o "houve troca" desmarcado é quase sempre esquecimento
        # de marcar a caixinha — melhor marcar do que perder o dado.
        if dados.get("peca_substituida") and not dados.get("houve_troca_peca"):
            dados["houve_troca_peca"] = True
        return dados


class ChamadoAnexoForm(BootstrapFormMixin, forms.ModelForm):
    """Anexa (ou troca) a OS digitalizada, inclusive depois do encerramento.

    Existe separado do encerramento porque nem sempre a folha assinada é
    digitalizada na hora — o scanner pode estar ocupado, e a OS não deve
    ficar travada esperando por isso.
    """

    class Meta:
        model = Chamado
        fields = ["arquivo_os"]
        widgets = {"arquivo_os": ArquivoProtegidoInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        protege_arquivo(self, "arquivo_os", "chamado_arquivo")

    def clean_arquivo_os(self):
        arquivo = _valida_arquivo_os(self.cleaned_data.get("arquivo_os"))
        if not arquivo:
            raise forms.ValidationError("Escolha o arquivo digitalizado.")
        return arquivo
