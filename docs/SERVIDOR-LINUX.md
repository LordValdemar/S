# 🐧 Configurando o servidor Linux (passo a passo)

Guia para preparar um servidor **Ubuntu Server 24.04 LTS** do zero, pensado para quem nunca usou Linux. Serve para os três casos:

| Onde | Siga |
|---|---|
| **Computador da loja** (PC, mini PC) | todos os passos |
| **Máquina virtual** para testes | passos 1 a 6 (no passo 1, use o [guia da VM](TESTE-MAQUINA-VIRTUAL.md)) |
| **VPS** (servidor na internet) | o Ubuntu já vem instalado: comece no passo 2. O IP fixo (passo 7) já vem do provedor |

Quando terminar, instale o painel: [na loja](INSTALACAO-LOCAL.md) ou [na VPS](HOSPEDAGEM.md).

> **Raspberry Pi?** Use o **Raspberry Pi OS** (instalado pelo [Raspberry Pi Imager](https://www.raspberrypi.com/software/)). No Imager, clique na engrenagem para já definir usuário, senha, Wi-Fi, fuso horário e ativar o SSH. Os passos 3, 5, 7, 8 e 10 deste guia valem igual para ele.

---

## 0. O mínimo de terminal que você precisa

O servidor é usado por comandos digitados. Estes resolvem quase tudo:

| Comando | O que faz |
|---|---|
| `pwd` | mostra em que pasta você está |
| `ls -la` | lista os arquivos da pasta |
| `cd pasta` / `cd ..` / `cd ~` | entra numa pasta / volta uma / vai para a sua pasta pessoal |
| `sudo comando` | roda como administrador (pede a **sua** senha; nada aparece enquanto digita, é normal) |
| `nano arquivo` | edita um arquivo de texto |
| `cat arquivo` | mostra o conteúdo de um arquivo |
| `Ctrl + C` | interrompe o comando que está rodando |
| `↑` (seta para cima) | repete comandos anteriores |
| `Tab` | completa nomes de arquivos e comandos |

**Usando o `nano`:** edite com as setas do teclado. `Ctrl + O` e depois `Enter` salva. `Ctrl + X` sai. `Ctrl + K` apaga a linha inteira.

> Para colar no terminal: no Windows (PowerShell), clique com o **botão direito**; no Mac e no Linux, use `Ctrl + Shift + V` (ou `Cmd + V` no Mac).

---

## 1. Instalar o Ubuntu Server (computador da loja)

**Você vai precisar:** o computador que será o servidor, um pendrive de 4 GB ou mais (ele será apagado) e, de preferência, **cabo de rede** ligando o servidor ao roteador. Um servidor no Wi-Fi funciona, mas é menos estável.

1. Baixe o **Ubuntu Server 24.04 LTS** em [ubuntu.com/download/server](https://ubuntu.com/download/server).
2. Grave o arquivo no pendrive com o [balenaEtcher](https://etcher.balena.io) (Windows, Mac e Linux) ou o [Rufus](https://rufus.ie) (Windows).
3. Ligue o servidor com o pendrive conectado e escolha iniciar por ele. Geralmente é uma tecla logo ao ligar, como `F12`, `F11`, `F8` ou `Esc`, dependendo do fabricante.
4. No instalador, use as setas, `Enter` e `Tab`:
   - **Idioma:** Português, ou English se preferir as mensagens em inglês (ajuda a pesquisar erros).
   - **Teclado:** *Portuguese (Brazil)* (layout ABNT2).
   - **Tipo de instalação:** *Ubuntu Server*.
   - **Rede:** se o cabo estiver ligado, ele pega um IP sozinho. Anote o IP que aparecer.
   - **Proxy e espelho:** deixe como está.
   - **Disco:** *Use an entire disk* (**apaga tudo** que estiver no disco).
   - **Perfil:** seu nome, o nome do servidor (ex.: `painel`), o seu usuário e uma **senha forte**.
   - **Ubuntu Pro:** pode pular.
   - **SSH:** marque **“Install OpenSSH server”**. É o que permite administrar o servidor do seu computador.
   - **Snaps adicionais:** não marque nenhum.
5. Aguarde, escolha **Reboot Now** e retire o pendrive quando pedir.

### Deixe o servidor ligar sozinho depois de queda de energia

Entre na **BIOS/UEFI** do computador (tecla `Del`, `F2` ou `F10` ao ligar) e procure uma opção como **“Restore on AC Power Loss”**, **“AC Power Recovery”** ou **“After Power Failure”**. Coloque em **Power On**. Assim, quando a luz voltar, o servidor liga sozinho, e as TVs voltam a funcionar sem ninguém apertar o botão.

---

## 2. Primeiro acesso

No próprio servidor, entre com o usuário e a senha criados. Veja o IP dele:

```bash
hostname -I        # o primeiro número, ex.: 192.168.0.50
```

Daqui em diante, é mais prático administrar **do seu computador**, pelo SSH: dá para copiar e colar os comandos deste guia. No PowerShell do Windows, ou no Terminal do Mac e do Linux:

```bash
ssh seu-usuario@192.168.0.50
```

Na primeira vez, ele pergunta se confia no servidor: digite `yes`. Depois, digite a senha.

> **VPS:** o provedor informa o IP e o usuário inicial (geralmente `root`): `ssh root@IP-DA-VPS`.

---

## 3. Atualizar o sistema

Sempre o primeiro passo num servidor novo:

```bash
sudo apt update && sudo apt upgrade -y
```

Se aparecer a mensagem *“System restart required”*, ou se o comando abaixo mostrar algo, reinicie:

```bash
cat /var/run/reboot-required 2>/dev/null && sudo reboot
```

(O `reboot` derruba a conexão SSH. Espere 1 minuto e conecte de novo.)

---

## 4. Fuso horário e nome do servidor

O fuso horário vale para os horários dos logs e das tarefas agendadas, como o backup das 4h. A programação das propagandas usa o `FUSO_HORARIO` do painel, que também é `America/Sao_Paulo` por padrão.

```bash
sudo timedatectl set-timezone America/Sao_Paulo
timedatectl                       # confira "Time zone" e "System clock synchronized: yes"
sudo hostnamectl set-hostname painel
```

Outros fusos: `America/Manaus`, `America/Cuiaba`, `America/Fortaleza`, `America/Recife`, `America/Belem`, `America/Rio_Branco`, `America/Noronha`. Liste todos com `timedatectl list-timezones | grep America`.

---

## 5. Usuário administrador e chave SSH

### Na VPS: crie um usuário seu (não use o `root` no dia a dia)

```bash
adduser admin                     # escolha uma senha forte (é a que o sudo vai pedir)
usermod -aG sudo admin
# Se você cadastrou a chave SSH ao criar a VPS, ela está no root: copie para o admin.
mkdir -p /home/admin/.ssh
cp ~/.ssh/authorized_keys /home/admin/.ssh/ 2>/dev/null && echo "chave copiada"
chown -R admin:admin /home/admin/.ssh
chmod 700 /home/admin/.ssh; chmod 600 /home/admin/.ssh/authorized_keys 2>/dev/null
```

A partir daqui, entre com `ssh admin@IP-DA-VPS`. Se a chave foi copiada, pule o próximo bloco.

### Em qualquer servidor: entre com chave SSH em vez de senha

A chave é um par de arquivos: a parte **privada** fica no seu computador e a **pública** vai para o servidor. É muito mais segura que senha. **No seu computador** (não no servidor):

```bash
ssh-keygen -t ed25519 -C "seu@email.com"          # Enter para o local padrão; defina uma senha para a chave
ssh-copy-id seu-usuario@192.168.0.50              # envia a chave pública para o servidor
```

> **No Windows**, o `ssh-copy-id` não existe. Use no PowerShell:
> ```powershell
> type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh seu-usuario@192.168.0.50 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
> ```

Teste: `ssh seu-usuario@192.168.0.50` agora entra sem pedir a senha do servidor (pode pedir a senha **da chave**).

### Desligue o login por senha (obrigatório na VPS, recomendado na loja)

> ⚠️ **Antes**, confirme num **segundo terminal** que o login com a chave funciona. Se não funcionar, não continue: você ficaria trancado para fora.

```bash
# "00-" faz este arquivo ser lido primeiro: o SSH usa a PRIMEIRA regra que encontra.
sudo tee /etc/ssh/sshd_config.d/00-seguranca.conf > /dev/null <<'FIM'
PasswordAuthentication no
PermitRootLogin no
KbdInteractiveAuthentication no
FIM
sudo sshd -t && sudo systemctl reload ssh
sudo sshd -T | grep -E '^(passwordauthentication|permitrootlogin)'   # deve mostrar "no" nos dois
```

**Guarde bem a chave privada** (o arquivo `~/.ssh/id_ed25519` no seu computador): sem ela, só dá para entrar pelo teclado do próprio servidor ou, na VPS, pelo console do provedor.

---

## 6. Atualizações automáticas de segurança

O Ubuntu Server já vem com o `unattended-upgrades`. Confirme que ele está ligado:

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades       # responda "Sim"/"Yes"
```

Ele instala sozinho, todo dia, as correções de segurança. Algumas só valem depois de reiniciar: reinicie o servidor de vez em quando, num horário sem movimento (ex.: domingo à noite), com `sudo reboot`.

> **VPS:** o instalador do painel (`instalar-vps.sh`) já faz este passo e os passos 8 e 9.

---

## 7. IP fixo (servidor da loja)

As TVs acessam o servidor pelo IP dele. Se o roteador trocar o IP, **as TVs param**. Escolha **uma** das opções:

### Opção A (recomendada): reserva no roteador

Na página do roteador (geralmente `http://192.168.0.1` ou `http://192.168.1.1`; o usuário e a senha costumam estar na etiqueta), procure **“Reserva de DHCP”**, **“IP fixo”** ou **“Endereço reservado”** e reserve o IP atual do servidor. Nada muda no servidor.

### Opção B: configurar o IP fixo no próprio servidor

Descubra o nome da placa de rede, o IP e o gateway (o roteador):

```bash
ip -br address          # ex.: "enp0s3   UP   192.168.0.50/24"  → a placa é enp0s3
ip route | grep default # ex.: "default via 192.168.0.1"         → o gateway é 192.168.0.1
```

Escolha um IP **fora** da faixa que o roteador distribui sozinho (veja na página do roteador; ex.: se ele distribui de `.100` a `.200`, use `.50`). Crie o arquivo:

```bash
sudo nano /etc/netplan/99-ip-fixo.yaml
```

Com este conteúdo, trocando `enp0s3`, o IP e o gateway pelos seus. **Use espaços, não Tab**, e mantenha o recuo exatamente assim:

```yaml
network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: false
      addresses:
        - 192.168.0.50/24
      routes:
        - to: default
          via: 192.168.0.1
      nameservers:
        addresses: [192.168.0.1, 1.1.1.1]
```

Aplique com segurança. O `netplan try` **desfaz sozinho em 2 minutos** se você perder a conexão:

```bash
sudo chmod 600 /etc/netplan/99-ip-fixo.yaml
sudo netplan try        # se tudo continuar funcionando, aperte Enter para confirmar
```

Se mudou o IP, reconecte o SSH no IP novo.

---

## 8. Firewall

O firewall bloqueia tudo que não for liberado.

**Servidor da loja:** libere o SSH e o painel **só para a rede da loja**. Troque `192.168.0.0/24` pela sua rede: se o IP do servidor é `192.168.1.50`, use `192.168.1.0/24`.

```bash
sudo ufw allow 22/tcp
sudo ufw allow from 192.168.0.0/24 to any port 5000 proto tcp
sudo ufw enable                   # responda "y"
sudo ufw status
```

**VPS:** não precisa fazer nada. O `instalar-vps.sh` libera só SSH (22), HTTP (80) e HTTPS (443).

> Se mudou a porta do SSH, libere a porta nova **antes** do `ufw enable`.

---

## 9. Proteção contra tentativas de invasão (VPS)

O **fail2ban** bloqueia por um tempo os IPs que erram a senha do SSH muitas vezes. Na VPS, o instalador do painel já ativa. Num servidor da loja, é opcional:

```bash
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd      # mostra quantos IPs foram bloqueados
```

---

## 10. Não deixar o servidor dormir (notebook ou PC)

Num notebook usado como servidor, impeça a suspensão e permita deixar a tampa fechada:

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
sudo sed -i 's/^#\?HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
sudo systemctl restart systemd-logind
```

Use também um **nobreak**: quedas de energia desligam o servidor e as TVs.

---

## 11. Instalar o painel

O servidor está pronto. Siga para:
- **Na loja:** [INSTALACAO-LOCAL.md](INSTALACAO-LOCAL.md), passo 2, opção “Raspberry Pi / Linux”
- **Na VPS:** [HOSPEDAGEM.md](HOSPEDAGEM.md), passo 4
- **Teste em VM:** [TESTE-MAQUINA-VIRTUAL.md](TESTE-MAQUINA-VIRTUAL.md), passos 3 e 4

---

## 12. Comandos do dia a dia

```bash
# Painel
systemctl status painel-propagandas              # está rodando? (q para sair)
sudo systemctl restart painel-propagandas        # reiniciar (depois de mudar a configuração)
journalctl -u painel-propagandas -f              # acompanhar os logs ao vivo (Ctrl+C para sair)
journalctl -u painel-propagandas --since today   # logs de hoje

# Servidor
df -h /                  # espaço em disco (fique de olho acima de 80%)
free -h                  # memória
uptime                   # há quanto tempo está ligado e a carga
sudo apt update && sudo apt upgrade -y   # atualizar tudo à mão
sudo reboot              # reiniciar
sudo poweroff            # desligar
```

Para ver o que mais ocupa espaço nos dados do painel:

```bash
sudo du -sh /opt/painel-propagandas/dados/*      # VPS
du -sh ~/painel-propagandas/dados/*              # loja (ajuste o caminho da pasta)
```

---

## 13. Problemas comuns

**“Permission denied (publickey)” ao entrar pelo SSH**: a chave não está no servidor ou você está usando outro usuário. Entre pelo teclado do servidor (ou pelo console do provedor, na VPS) e confira o arquivo `~/.ssh/authorized_keys` do usuário.

**“Connection refused” ou “timed out” no SSH**
- O servidor está ligado e na rede? Teste com `ping 192.168.0.50`.
- O IP mudou? Veja no servidor com `hostname -I` e faça a reserva (passo 7).
- Na VPS, a porta 22 está liberada no firewall do provedor?

**Sem internet depois de configurar o IP fixo**: o `netplan try` desfaz sozinho se você não confirmar. Se confirmou e perdeu a rede, no teclado do servidor rode `sudo rm /etc/netplan/99-ip-fixo.yaml && sudo netplan apply` para voltar ao DHCP, e confira o nome da placa, o gateway e o recuo do arquivo.

**“sudo: unable to resolve host”** depois de trocar o nome: adicione o nome novo ao arquivo de hosts com `echo "127.0.1.1 painel" | sudo tee -a /etc/hosts`.

**O teclado digita caracteres errados no console** (ex.: `ç`, acentos): `sudo dpkg-reconfigure keyboard-configuration` e escolha *Portuguese (Brazil)*.

**Disco cheio**: veja o que ocupa com o comando `du` do passo 12. Normalmente são vídeos grandes ou backups. Diminua `BACKUP_MANTER` na configuração do painel ou aumente o disco (na VPS, pelo painel do provedor).
