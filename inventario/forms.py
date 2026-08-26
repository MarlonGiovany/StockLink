from django import forms

from .models import (
    Aditivo,
    Cliente,
    Contrato,
    Equipamento,
    Fornecedor,
    Locacao,
    Manutencao,
    Produto,
)


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


class FornecedorForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = ["nome", "cnpj", "telefone", "email", "observacoes"]
        widgets = {"observacoes": forms.Textarea(attrs={"rows": 2})}


class ClienteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "documento", "telefone", "email", "endereco", "observacoes"]
        widgets = {"observacoes": forms.Textarea(attrs={"rows": 2})}


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
        }

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get("arquivo")
        if arquivo and getattr(arquivo, "name", "") and not arquivo.name.lower().endswith(".pdf"):
            raise forms.ValidationError("O contrato precisa estar em PDF (.pdf).")
        return arquivo


class AditivoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Aditivo
        fields = ["tipo", "descricao", "valor", "data", "arquivo", "observacoes"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get("arquivo")
        if arquivo and getattr(arquivo, "name", "") and not arquivo.name.lower().endswith(".pdf"):
            raise forms.ValidationError("O aditivo precisa estar em PDF (.pdf).")
        return arquivo
