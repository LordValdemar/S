# 📺 Painel de Propagandas

Sistema de **sinalização digital** para exibir propagandas em TVs e monitores de estabelecimentos comerciais (padarias, lojas, restaurantes, consultórios…). Feito em **Python + Flask**.

## Recursos

**Para quem usa**
- Painel no navegador (computador ou celular) para enviar imagens e vídeos, definir o tempo de cada um, mudar a ordem, ativar ou desativar e excluir.
- **Período de validade** por propaganda (ex.: promoção de 01/10 a 15/10).
- **Letreiro** com texto rolando no rodapé.
- Tela de exibição em tela cheia que recebe as mudanças sozinha e continua passando as propagandas se a rede cair.

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
- Início automático com o computador (systemd no Linux, script no Windows) e modo quiosque para a TV.

## Instalação rápida

Precisa do **Python 3.10 ou mais novo** ([python.org](https://www.python.org/downloads/)).

### Linux / Raspberry Pi (recomendado, como serviço)

```bash
git clone <este-repositório> painel-propagandas
cd painel-propagandas
sudo ./deploy/instalar-linux.sh
```

Pronto: o painel inicia sozinho sempre que o computador ligar e reinicia se travar.

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
3. Envie as propagandas.
4. Na TV, abra **http://IP-DO-COMPUTADOR:5000/player** e clique (ou aperte **F**) para tela cheia.

> Para descobrir o IP: no Linux, `hostname -I`; no Windows, `ipconfig` (procure “Endereço IPv4”).

## TV em modo quiosque (abre sozinha, em tela cheia)

No computador ligado à TV (ex.: Raspberry Pi com Raspberry Pi OS):

```bash
mkdir -p ~/.config/autostart
cp deploy/tela-quiosque.desktop ~/.config/autostart/
```

Se o servidor estiver em **outro** computador, edite o arquivo e troque `localhost` pelo IP dele.

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
python -m pytest                                  # testes automáticos
flask --app propagandas run --debug               # servidor com recarga automática
```

### Estrutura

```
servidor.py              # inicia em produção (Waitress + backup automático)
gerenciar.py             # comandos de administração
propagandas/
├── __init__.py          # create_app: configuração, logs, segurança
├── db.py                # SQLite e migrações (para mudar o banco, adicione em MIGRACOES)
├── auth.py              # login, usuários, papéis, CSRF, limite de tentativas
├── painel.py            # cadastro das propagandas
├── exibicao.py          # tela da TV, API /api/playlist, /midia, /saude
├── midia.py             # identificação dos arquivos pelo conteúdo
├── backup.py            # backup e restauração
├── templates/           # páginas HTML
└── static/              # CSS e JavaScript
deploy/                  # serviço systemd, instalador, Windows, quiosque, Caddy
tests/                   # testes automáticos (pytest)
```
