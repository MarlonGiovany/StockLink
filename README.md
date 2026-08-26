# 📦 StockLink — Controle de Equipamentos e Patrimônio

Sistema web (Django) para a INFORLINK controlar equipamentos, locações,
manutenções, contratos e movimentações. Roda localmente, de graça, com banco SQLite.

## Como rodar (toda vez)

Abra o terminal **dentro desta pasta** (`C:\Users\RUAN\Desktop\stocklink`) e:

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

- **Login** com usuário e senha + **permissões** (admin vs. operador)
- **Produtos**: os tipos de item que a empresa trabalha (Desktop, Notebook,
  Monitor, Impressora, Scanner, Estabilizador, Transformador). A aba
  **Equipamentos** abre num painel com um botão por produto — clica no produto
  e vê só aquela lista; o botão **Todos** mostra a lista completa. Produtos
  novos entram pelo botão **"+ Adicionar novo produto"** na tela de cadastro
  de equipamento (é só escrever o nome).
- **Equipamentos**: produto, marca, modelo, nº série, nº patrimônio, valor de
  compra, data de aquisição, fornecedor, localização e status
- **Ficha técnica** (só para **Desktop** e **Notebook**): ao escolher um desses
  produtos, o cadastro abre mais três campos — **processador**, **memória RAM**
  e **armazenamento (SSD/HD)**. Para os outros produtos esses campos nem
  aparecem. Em `/admin/` → **Produtos** dá para ligar isso em outro produto
  (campo "Pede configuração").
- **Cores de manutenção** 🟢🟡🟠🔴: cada equipamento tem uma "bolinha" que
  mostra quantas vezes já foi pra manutenção — 🟢 até 2 · 🟡 3ª · 🟠 4ª ·
  🔴 5ª ou mais. Quanto mais vermelho, mais problema o equipamento dá.
- **Manutenções**: histórico completo por equipamento
- **Locações**: cliente, valor, datas de início/fim, com devolução. Ao registrar
  a locação você já pode **escolher um contrato que existe** — a lista mostra
  só os contratos daquele cliente. Um mesmo contrato atende **várias máquinas**,
  então não precisa mais criar um contrato por equipamento. Se a locação já
  estiver registrada, dá para vincular depois pela ficha do equipamento.
- **Contratos**: cada contrato mostra a lista de **máquinas vinculadas** a ele,
  e a lista de contratos traz a coluna **Máquinas** com a quantidade.
  Anexa o PDF do contrato (feito no Word e salvo em PDF), com
  **busca**, **ordenação** (por número ou data) e **filtro por período**. O
  valor do contrato é **manual**. Dá pra criar o contrato direto da locação de
  um equipamento — o cliente já vem preenchido e o nº do contrato aparece na
  ficha do equipamento.
- **Aditivos** (dentro de cada contrato): histórico das alterações, marcando
  **adição** ou **remoção** de equipamento, com descrição, data, valor e PDF.
  É só registro — **não altera** o valor do contrato.
- **Histórico de movimentações**: registro append-only de tudo (cadastro,
  edição, mudança de local/status, manutenção, locação, devolução)
- **Clientes** e **Fornecedores**
- **Painel administrativo** completo em `/admin/`

## Estrutura

```
stocklink/
├── config/         # configurações do Django
├── inventario/     # o app principal (models, views, forms, admin)
├── templates/      # páginas HTML (Bootstrap)
├── db.sqlite3      # banco de dados (NÃO apagar — são seus dados!)
├── _backup_*/      # cópias de segurança do banco (feitas antes de mudanças)
├── media/          # PDFs dos contratos e aditivos (NÃO apagar!)
└── venv/           # ambiente Python isolado
```

## Importar dados do protótipo antigo (já feito uma vez)

```bat
python manage.py importar_json "caminho\para\equipamentos.json"
```

## 💾 Backup (IMPORTANTE)

Seus dados ficam em **dois lugares**. Para um backup completo, copie os dois
para um lugar seguro (pen drive, nuvem):

1. **`db.sqlite3`** — o banco de dados (equipamentos, clientes, contratos...).
2. **pasta `media`** — os PDFs dos contratos e aditivos.

**Não apague** nenhum dos dois.
