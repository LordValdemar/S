# 📺 Painel de Propagandas

Sistema de **sinalização digital** para exibir propagandas em TVs e monitores de estabelecimentos comerciais (padarias, lojas, restaurantes, consultórios…). Feito em **Python + Flask**.

## Recursos

**Para quem usa**
- Painel no navegador (computador ou celular) para enviar imagens e vídeos, definir o tempo de cada um, mudar a ordem, ativar ou desativar e excluir.
- **Agendamento**: período de validade (ex.: 01/10 a 15/10), **dias da semana** e **faixa de horário** (ex.: café da manhã de seg a sex, das 06:00 às 10:00).
- **Várias telas e grupos de telas**: cada propaganda vai para todas as telas, para telas específicas ou para grupos (ex.: “Lojas de SP”).
- **Letreiro** com texto rolando no rodapé, geral ou próprio de cada tela.
- Tela de exibição em tela cheia que recebe as mudanças sozinha, pré-carrega as mídias e continua passando as propagandas se a rede cair.

**Monitoramento e relatórios**
- Status de cada tela em tempo real: **online/offline**, último contato, IP e **o que está exibindo agora**.
- **Alertas** por e-mail e/ou webhook (Slack, Teams, Discord, Google Chat) quando uma tela cai e quando ela volta.
- **Relatório de exibições** (proof of play): quantas vezes e por quanto tempo cada propaganda passou em cada tela, com filtro por período e tela e **exportação CSV** para o Excel. Serve para prestar contas a anunciantes.
- As exibições são guardadas na própria TV quando a rede cai e enviadas quando ela volta, sem duplicar.

**Para quem instala e mantém**
- Servidor de produção (**Waitress**), que funciona em Linux, Windows, macOS e Raspberry Pi.
- **Login com usuários e papéis**: *Administrador* (gerencia usuários) e *Editor* (cuida das propagandas).
- Senhas guardadas com hash forte (scrypt). Trocar a senha desconecta os outros aparelhos.
- Bloqueio de login após 5 tentativas erradas em 15 minutos.
- Proteção **CSRF**, cookies `HttpOnly`/`SameSite` e cabeçalhos de segurança (**CSP**, anti-clickjacking).
- Arquivos enviados são conferidos **pelo conteúdo**, não só pela extensão, e salvos com nome aleatório.
- Banco **SQLite** com migrações versionadas.
- **Backup automático diário** (banco + mídias), guardando os últimos 7, com restauração por comando.
- **Logs de auditoria** (quem enviou, alterou ou excluiu o quê, logins e tentativas erradas).
- Endereço `/saude` para monitoramento.
- Início automático com o computador (systemd no Linux, script no Windows), **Docker** e modo quiosque para a TV.
- Testes automáticos a cada envio ao GitHub (**GitHub Actions**, Python 3.10 a 3.13 + imagem Docker).

## Instalação rápida

Precisa do **Python 3.10 ou mais novo** ([python.org](https://www.python.org/downloads/)).

### Linux / Raspberry Pi (recomendado, como serviço)

```bash
git clone <este-repositório> painel-propagandas
cd painel-propagandas
sudo ./deploy/instalar-linux.sh
```

Pronto: o painel inicia sozinho sempre que o computador ligar e reinicia se travar.

### Docker

```bash
mkdir -p dados && sudo chown 1000 dados   # o container roda como usuário sem privilégios (uid 1000)
docker compose up -d
docker compose exec painel python gerenciar.py listar-usuarios
```

### Windows

Dê dois cliques em `deploy\iniciar-windows.bat`. Na primeira vez ele instala tudo.

Para iniciar junto com o Windows: aperte `Win + R`, digite `shell:startup` e coloque um **atalho** para o `iniciar-windows.bat` na pasta que abrir.

### Manual (qualquer sistema)

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python servidor.py
```

## Primeiro acesso

1. Abra **http://localhost:5000/** (ou `http://IP-DO-COMPUTADOR:5000/` de outro aparelho da rede).
2. Crie o **usuário administrador**. Essa tela só aparece uma vez.
3. Em **Telas**, cadastre cada TV (ex.: “Loja Centro: Balcão”). Cada uma recebe um **endereço próprio**, como `http://192.168.0.10:5000/tela/Ab3dE5fG7hJk`.
4. Envie as propagandas. Em **Agendamento e telas**, escolha dias, horários e em quais telas cada uma aparece.
5. Na TV, abra o endereço da tela e clique (ou aperte **F**) para tela cheia.

> O endereço da tela funciona como uma senha: quem não o tem não vê nem altera nada daquela tela. Se ele vazar, use **Gerar novo endereço**.
>
> O endereço geral `/player` continua funcionando, mas mostra só as propagandas marcadas para “Todas as telas” e **não** aparece no monitoramento nem nos relatórios.

> Para descobrir o IP: no Linux, `hostname -I`; no Windows, `ipconfig` (procure “Endereço IPv4”).

## TV em modo quiosque (abre sozinha, em tela cheia)

No computador ligado à TV (ex.: Raspberry Pi com Raspberry Pi OS):

```bash
mkdir -p ~/.config/autostart
cp deploy/tela-quiosque.desktop ~/.config/autostart/
```

Edite o arquivo e troque `http://localhost:5000/player` pelo **endereço da tela** (veja em **Telas** no painel). Se o servidor estiver em outro computador, use o IP dele.

O modo quiosque também libera o **som dos vídeos**. Sem ele, os navegadores bloqueiam o som automático e os vídeos tocam mudos.

## Administração pela linha de comando

```bash
python gerenciar.py listar-usuarios
python gerenciar.py criar-usuario joao --papel editor
python gerenciar.py trocar-senha dono        # esqueceu a senha? use este
python gerenciar.py backup                   # backup na hora
python gerenciar.py restaurar dados/backups/backup-20261001-030000.zip
```

> **Antes de restaurar, pare o servidor** (`sudo systemctl stop painel-propagandas` no Linux). Os dados atuais não são apagados: ficam guardados em `dados/antes-da-restauracao-<data>/`.

## Alertas de tela offline

Configure pelo menos um canal pelas variáveis de ambiente. Depois use **Telas → Enviar alerta de teste** para conferir.

**Webhook** (Slack, Microsoft Teams, Discord, Google Chat ou qualquer serviço que receba JSON):

```bash
ALERTA_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
```

**E-mail** (exemplo com Gmail; crie uma “senha de app” na sua conta Google):

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORTA=587
SMTP_USUARIO=voce@gmail.com
SMTP_SENHA=sua-senha-de-app
ALERTA_EMAILS=dono@loja.com.br,gerente@loja.com.br
```

O alerta é enviado uma vez quando a tela fica mais de `ALERTA_OFFLINE_MIN` minutos (padrão 5) sem comunicação, e outra vez quando ela volta.

## Onde ficam os dados

Tudo fica na pasta `dados/`. **É ela que você deve copiar** para levar o sistema a outro computador.

```
dados/
├── banco.sqlite3     # propagandas, usuários e configurações
├── midia/            # imagens e vídeos enviados
├── backups/          # backups automáticos (um por dia, guarda os 7 últimos)
├── logs/painel.log   # registro de acessos e alterações
└── chave_secreta     # chave das sessões (não compartilhe)
```

Os backups ficam no mesmo disco. Para proteção contra defeito no computador, copie a pasta `dados/backups/` de vez em quando para um pendrive ou para a nuvem.

## Configurações (variáveis de ambiente)

| Variável | Padrão | Descrição |
|---|---|---|
| `PORTA` | `5000` | Porta do servidor |
| `HOST` | `0.0.0.0` | `0.0.0.0` aceita a rede local; `127.0.0.1` aceita só o próprio computador |
| `PASTA_DADOS` | `./dados` | Onde ficam banco, mídias, backups e logs |
| `TAMANHO_MAX_MB` | `500` | Tamanho máximo de cada envio |
| `BACKUP_MANTER` | `7` | Quantos backups diários guardar (`0` desliga o backup automático) |
| `FUSO_HORARIO` | `America/Sao_Paulo` | Fuso usado no agendamento e nos relatórios (ex.: `America/Manaus`) |
| `RETER_EXIBICOES_DIAS` | `365` | Por quantos dias guardar o histórico de exibições |
| `ALERTA_OFFLINE_MIN` | `5` | Minutos sem comunicação até alertar |
| `ALERTA_WEBHOOK` | (vazio) | URL do webhook de alertas |
| `ALERTA_EMAILS` | (vazio) | E-mails que recebem alertas, separados por vírgula |
| `SMTP_HOST`, `SMTP_PORTA`, `SMTP_USUARIO`, `SMTP_SENHA`, `SMTP_REMETENTE` | (vazio), `587` | Servidor de e-mail. Porta 465 usa SSL; as outras usam STARTTLS |
| `COOKIE_SEGURO` | desligado | `1` quando o acesso for por **HTTPS** |
| `ATRAS_DE_PROXY` | desligado | `1` quando houver Caddy/Nginx na frente |
| `CHAVE_SECRETA` | gerada sozinha | Chave das sessões (opcional) |

No Linux com o serviço, coloque as variáveis no arquivo `/etc/systemd/system/painel-propagandas.service` (linhas `Environment=`) e rode `sudo systemctl daemon-reload && sudo systemctl restart painel-propagandas`.

## Acesso pela internet (HTTPS)

Na rede local, o acesso direto já é suficiente. **Se o painel for aberto pela internet, use HTTPS**, senão a senha trafega sem criptografia. O jeito mais simples é o [Caddy](https://caddyserver.com), que obtém o certificado sozinho. Veja o exemplo em `deploy/Caddyfile.exemplo` e rode o painel com:

```bash
HOST=127.0.0.1 ATRAS_DE_PROXY=1 COOKIE_SEGURO=1 python servidor.py
```

## Desenvolvimento

```bash
pip install -r requirements.txt -r requirements-dev.txt
ruff check .                                      # estilo e erros comuns
python -m pytest                                  # testes automáticos
flask --app propagandas run --debug               # servidor com recarga automática
```

### Estrutura

```
servidor.py              # inicia em produção (Waitress + tarefas em segundo plano)
gerenciar.py             # comandos de administração
propagandas/
├── __init__.py          # create_app: configuração, logs, segurança
├── db.py                # SQLite e migrações (para mudar o banco, adicione em MIGRACOES)
├── auth.py              # login, usuários, papéis, CSRF, limite de tentativas
├── painel.py            # cadastro das propagandas (agendamento e destinos)
├── agenda.py            # fuso horário e regras de agendamento
├── telas.py             # telas, grupos e monitoramento
├── exibicao.py          # player, API das TVs (playlist e pulso), /midia, /saude
├── alertas.py           # alertas de tela offline (e-mail e webhook)
├── relatorios.py        # relatório de exibições e CSV
├── tarefas.py           # segundo plano: monitoramento, backup, limpeza
├── midia.py             # identificação dos arquivos pelo conteúdo
├── backup.py            # backup e restauração
├── templates/           # páginas HTML
└── static/              # CSS e JavaScript
deploy/                  # serviço systemd, instalador, Windows, quiosque, Caddy
Dockerfile, docker-compose.yml
.github/workflows/       # testes automáticos no GitHub
tests/                   # testes automáticos (pytest)
```
