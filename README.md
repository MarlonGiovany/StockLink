# 📦 StockLink — Controle de Equipamentos, Contratos e Chamados

Sistema web (Django) da **INFORLINK** para controlar o parque de máquinas:
equipamentos, locações, contratos, manutenções e os **chamados técnicos com
Ordem de Serviço**. Funciona no computador, no tablet e no celular.

- **Produção:** roda no **PythonAnywhere**, com banco SQLite.
- **Desenvolvimento:** roda localmente no Windows, também com SQLite.

## Como rodar no computador (toda vez)

Abra o terminal **dentro da pasta do projeto** e:

```bat
venv\Scripts\activate
python manage.py runserver
```

Depois acesse no navegador: **http://127.0.0.1:8000**

Para parar o servidor: tecle **Ctrl + C** no terminal.

> 🆕 Vai instalar em outro computador? Veja o passo a passo em **`COMO_RODAR.md`**.

## Usuários e senhas

As credenciais de acesso não ficam neste repositório. Consulte o arquivo
guardado separadamente (fora do Git).

## O que o sistema faz

### Acesso e perfis

- **Login** com usuário e senha (com opção de ver a senha digitada).
- **Limite de tentativas:** errou a senha 5 vezes em 15 minutos, o login
  daquele usuário fica bloqueado por um tempo naquele endereço.
- **Perfis**, escolhidos na tela **Usuários e permissões**:
  - **Analista** (o login `Admin`) — o único que dá permissões, escolhe o
    perfil de cada pessoa e troca a senha de quem esqueceu;
  - **Superusuário** — faz tudo nas telas, mas não mexe em permissões;
  - **Recepção** — tudo no sistema, inclusive contratos e excluir, menos dar
    permissões;
  - **Técnico** — cadastra equipamento, registra manutenção e cuida só das
    OS dele.
- **Áreas restritas** liberadas pessoa por pessoa pelo Analista: a aba
  **Contratos** e os **PDFs anexados**.
- Página de **acesso negado** clara, explicando o que faltou.

### Equipamentos

- **Produtos**: os tipos de item que a empresa trabalha (Desktop, Notebook,
  Tablet, Monitor, Impressora, Scanner, Estabilizador, Transformador). A aba
  **Equipamentos** abre num painel com um botão por produto; o botão
  **Todos** mostra a lista completa. Produtos novos entram pelo botão
  **"+ Adicionar novo produto"** no cadastro de equipamento.
- **Cadastro**: produto, marca, modelo, nº de série, **INF** (a etiqueta
  colada na máquina), valor de compra, data de aquisição, fornecedor,
  localização e status (Disponível, Locado, Em manutenção, Baixado).
- **Ficha técnica** (Desktop e Notebook): processador, memória RAM e
  armazenamento. Em `/admin/` → **Produtos** dá para ligar isso em outro
  produto (campo "Pede configuração").
- **Cores de manutenção** 🟢🟡🟠🔴: a "bolinha" mostra quantas vezes a
  máquina já foi pra manutenção — 🟢 até 2 · 🟡 3ª · 🟠 4ª · 🔴 5ª ou mais.
- **Manutenções**: histórico completo por equipamento.
- Equipamento **locado não pode ser excluído** — a tela explica o motivo.

### Clientes e fornecedores

- Cadastro com **máscara automática** de CPF/CNPJ e telefone.
- Aviso quando já existe um **cliente parecido** (não barra, só avisa).
- Lista de clientes em **ordem alfabética** e com a **quantidade de máquinas
  locadas hoje** — o número abre a lista dessas máquinas.
- Clientes e fornecedores podem ser **editados e excluídos** pelo sistema.

### Locações

- Cliente, valor, datas de início/fim e devolução.
- Ao registrar, já dá para **escolher o contrato** do cliente. Um contrato
  atende **várias máquinas**; dá para vincular depois pela ficha do
  equipamento.
- Não deixa a mesma máquina ter **duas locações ativas**.
- **Valor em lote**: ajusta o valor de várias máquinas do contrato de uma vez.

### Contratos

- Não têm número: cada contrato é identificado por **cliente + data**
  (ex.: "Padaria Silva, 12/03/2025").
- **Vigência de 1 ano com renovação automática.** A lista avisa quando o
  aniversário do contrato está chegando (15 dias antes) — é aviso de
  renovação, não de vencimento.
- Mostra as **máquinas vinculadas**, o **valor total cobrado** delas e o
  **valor do contrato**, que é manual.
- Anexa o **PDF do contrato**, com busca, ordenação e filtro por período.
- **Aditivos**: histórico de adição ou remoção de máquinas (várias de uma
  vez, cada uma com seu valor), com data e PDF. É só registro — não altera o
  valor do contrato.
- Os PDFs **não têm link público**: só abre quem tem permissão.

### Chamados e Ordem de Serviço

- A recepção abre o chamado: cliente, máquina, o que fazer, técnico
  designado e urgência (🔴 Urgente · 🟡 Normal · 🟢 Leve).
- O nº do chamado é o **nº da OS**. A OS sai **impressa numa folha A4** e,
  depois do atendimento, a folha assinada pode ser **anexada digitalizada**
  (PDF ou imagem).
- No encerramento o técnico registra o que foi feito, se houve **troca de
  peça** e observações. O sistema grava sozinho a hora de abertura e de
  encerramento.
- **Painel da área técnica** para ficar numa TV/monitor: letra grande,
  atualiza sozinho em segundos quando entra chamado novo, com **bips de
  alerta** para chamado aberto há mais de 24 horas.
- **Histórico** com o tempo de cada atendimento. Encerrados saem da frente,
  a um clique de distância, e podem ser excluídos pelo Analista (com opção de
  recomeçar a numeração em 0001).

### Planilhas em Excel

- Baixa em **Excel** a lista de equipamentos do filtro atual e as **máquinas
  locadas de cada cliente**, com valores como número (dá para somar e
  filtrar).

### Outros

- **Histórico de movimentações**: registro de tudo que acontece
  (cadastro, edição, mudança de local/status, manutenção, locação, devolução)
  — só acrescenta, nunca apaga.
- **Tema escuro**, botão no topo da tela.
- **Tema de Natal**, que liga sozinho de 1º/dez a 6/jan.
- **Painel administrativo** em `/admin/`, com o visual do StockLink e
  funcionando no celular.

## Comandos úteis

Rodam no terminal, com o `venv` ativado. Os de importação mostram o que vão
fazer antes de gravar.

```bat
:: Importar clientes de uma planilha Excel (--simular só mostra)
python manage.py importar_clientes "caminho\clientes.xlsx" --simular

:: Cadastrar em lote as máquinas de um cliente, já locadas para ele
python manage.py importar_maquinas "caminho\maquinas.csv" --cliente 77

:: Importar o protótipo antigo (já feito uma vez)
python manage.py importar_json "caminho\equipamentos.json"
```

## Estrutura

```
StockLink/
├── config/         # configurações do Django
├── inventario/     # o app principal (models, views, forms, admin, permissões)
├── templates/      # páginas HTML (Bootstrap)
├── db.sqlite3      # banco de dados (NÃO apagar — são seus dados!)
├── media/          # PDFs dos contratos, aditivos e OS (NÃO apagar!)
└── venv/           # ambiente Python isolado
```

## 💾 Backup (IMPORTANTE)

Seus dados ficam em **dois lugares**. Para um backup completo, copie os dois
para um lugar seguro (pen drive, nuvem):

1. **`db.sqlite3`** — o banco de dados (equipamentos, clientes, contratos,
   chamados...).
2. **pasta `media`** — os PDFs dos contratos, dos aditivos e as OS
   digitalizadas.

**Não apague** nenhum dos dois.
