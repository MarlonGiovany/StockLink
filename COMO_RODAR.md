# 🚀 Como rodar o StockLink em outra máquina (passo a passo)

Guia para rodar o sistema do zero em um computador novo (Windows + VS Code).

---

## 1. Instalar o Python (se ainda não tiver)

1. Baixe em: https://www.python.org/downloads/
2. **MUITO IMPORTANTE:** na primeira tela do instalador, marque a caixa
   **"Add Python to PATH"** antes de clicar em Install.
3. Para conferir, abra o terminal e digite:
   ```
   python --version
   ```
   Tem que aparecer algo como `Python 3.12` (ou superior).

---

## 2. Abrir a pasta no VS Code

1. Abra o **VS Code**.
2. Menu **File → Open Folder** e escolha a pasta `stocklink`.
3. Abra um terminal dentro do VS Code: menu **Terminal → New Terminal**.

> Se o terminal abrir como "PowerShell" e der erro de permissão no passo 3,
> troque para o terminal **Command Prompt (cmd)**: clique na setinha ▼ ao
> lado do "+" no canto do terminal e escolha **Command Prompt**.

> 📦 **Recebeu o projeto em ZIP?** Descompacte primeiro (clique direito no
> arquivo → **Extrair tudo...**) e só então abra a pasta no VS Code. Não dá
> para rodar de dentro do ZIP.

> ℹ️ A pasta `venv` **não vem** no ZIP de propósito: ela guarda o caminho do
> computador de origem e não funcionaria aqui. Você cria a sua no passo 3.
> (Se em algum momento aparecer uma `venv` que veio de outra máquina, pode
> apagar sem medo: **não** é onde ficam os dados.)

---

## 3. Criar o ambiente Python e instalar o Django

No terminal (dentro da pasta do projeto), rode **uma vez** estes comandos:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Se aparecer `(venv)` no início da linha do terminal, deu certo. ✅

---

## 4. Preparar o banco de dados

> **Opção A — começar com os dados que já existem (é o seu caso):** o arquivo
> `db.sqlite3` veio junto no ZIP, já com equipamentos, clientes, fornecedores,
> contratos e locações cadastrados (as quantidades mudam conforme o uso —
> confira direto no sistema, não neste guia). **Pule este passo**, o banco já
> está pronto. A pasta `media` traz os PDFs dos contratos — mantenha.

> **Opção B — começar do zero (sem dados):** se não veio o `db.sqlite3`,
> rode os comandos abaixo para criar o banco e os usuários `admin` e `operador`:

```bat
python manage.py migrate
python setup_inicial.py
```

(o `setup_inicial.py` vai pedir o e-mail e as senhas do `admin` e do
`operador` no terminal — nenhuma senha fica salva no código)

---

## 5. Rodar o sistema

```bat
python manage.py runserver
```

Agora abra o navegador em: **http://127.0.0.1:8000**

Para **parar** o servidor: tecle **Ctrl + C** no terminal.

---

## Próximas vezes (atalho)

Depois de instalado, para rodar de novo é só:

```bat
venv\Scripts\activate
python manage.py runserver
```

---

## Usuários de teste

As credenciais de acesso não ficam neste repositório por segurança.
Consulte o arquivo guardado separadamente (fora do Git). Troque as senhas
padrão antes de usar pra valer (em `/admin/`).

---

## O que o sistema faz

- **Equipamentos**: cadastro, busca, status e localização.
- **Cores de manutenção** 🟢🟡🟠🔴: uma "bolinha" por equipamento mostra
  quantas vezes ele já foi pra manutenção (quanto mais vermelho, mais problema).
- **Locações**: aluguel de equipamento para clientes, com devolução.
- **Contratos** (aba **Contratos**): anexa o PDF do contrato, com busca,
  ordenação e filtro por data. Dá pra criar o contrato direto da locação do
  equipamento (o número do contrato aparece na ficha do equipamento).
- **Aditivos** dentro de cada contrato: histórico de **adições/remoções** de
  equipamentos, com data e valor — só registro, **não muda** o valor do
  contrato (que é manual).
- **Painel administrativo** completo em `/admin/`.

---

## 💾 Backup (IMPORTANTE)

Seus dados ficam em **dois lugares**. Para um backup completo, copie os dois:

1. **`db.sqlite3`** — o banco de dados (equipamentos, clientes, contratos...).
2. **pasta `media`** — os PDFs dos contratos e aditivos.

Guarde os dois num lugar seguro (pen drive, nuvem). **Não apague** nenhum dos dois.

---

## Deu algum erro?

- **"python não é reconhecido"** → o Python não foi instalado com a opção
  "Add to PATH". Reinstale marcando essa caixa.
- **Erro de permissão no `activate` (PowerShell)** → use o terminal
  **Command Prompt (cmd)** em vez do PowerShell (veja a dica no passo 2).
- **"No module named django"** → você esqueceu de ativar o `venv`
  (`venv\Scripts\activate`) ou de rodar o `pip install -r requirements.txt`.
- **PDF do contrato não abre** → confirme que a pasta `media` veio junto e
  está dentro da pasta do projeto.
