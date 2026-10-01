# 📺 Painel de Propagandas

Programa simples, feito em **Python + Flask**, para exibir propagandas em TVs e monitores de estabelecimentos comerciais (padarias, lojas, restaurantes, consultórios…).

## O que ele faz

- **Painel de controle** no navegador para:
  - enviar imagens (JPG, PNG, GIF, WEBP) e vídeos (MP4, WEBM);
  - definir quanto tempo cada imagem fica na tela (vídeos tocam até o fim);
  - mudar a ordem, ativar ou desativar e excluir propagandas;
  - programar um **período de validade** (ex.: promoção só de 01/10 a 15/10);
  - escrever um **letreiro** com texto rolando no rodapé.
- **Tela de exibição** em tela cheia, que alterna as propagandas em loop e recebe as mudanças do painel automaticamente, sem precisar recarregar.
- Continua exibindo a última lista se a conexão com o servidor cair.
- Senha opcional para proteger o painel.

## Como rodar

```bash
# 1. (opcional) crie um ambiente virtual
python3 -m venv .venv
source .venv/bin/activate        # no Windows: .venv\Scripts\activate

# 2. instale a dependência
pip install -r requirements.txt

# 3. inicie o programa
python app.py
```

Depois abra:

| Endereço | Para quê |
|---|---|
| http://localhost:5000/ | Painel de controle (cadastrar propagandas) |
| http://localhost:5000/player | Tela de exibição (abrir na TV) |

Na tela de exibição, **clique** ou aperte **F** para entrar em tela cheia.

### Usando em outro computador da rede

O servidor aceita conexões da rede local. Descubra o IP do computador que roda o programa (ex.: `192.168.0.10`) e, na TV ou no outro computador, abra `http://192.168.0.10:5000/player`. Assim você pode controlar as propagandas pelo celular, abrindo `http://192.168.0.10:5000/` no navegador.

### Protegendo o painel com senha

```bash
SENHA_ADMIN=minhasenha python app.py          # Linux/macOS
set SENHA_ADMIN=minhasenha && python app.py   # Windows (cmd)
```

O navegador vai pedir usuário e senha. O usuário pode ser qualquer um; só a senha é verificada. A tela de exibição continua aberta, sem senha.

### Outras configurações (variáveis de ambiente)

| Variável | Padrão | Descrição |
|---|---|---|
| `PORTA` | `5000` | Porta do servidor |
| `PASTA_MIDIA` | `./midia` | Onde os arquivos enviados ficam salvos |
| `ARQUIVO_DADOS` | `./playlist.json` | Arquivo com a lista de propagandas |
| `SENHA_ADMIN` | (vazio) | Senha do painel |

## Dica: TV com Raspberry Pi ou mini PC (modo quiosque)

Para a tela abrir sozinha, em tela cheia e **com som nos vídeos**, inicie o Chromium assim:

```bash
chromium --kiosk --autoplay-policy=no-user-gesture-required http://localhost:5000/player
```

Sem essa opção, os navegadores costumam bloquear o som automático. Nesse caso o programa toca os vídeos sem som.

## Testes

```bash
pip install pytest
python -m pytest
```

## Estrutura

```
app.py                 # servidor: painel, envio de arquivos e API da playlist
templates/admin.html   # página do painel de controle
templates/player.html  # tela de exibição (loop, transição e letreiro)
tests/test_app.py      # testes automáticos
```
