"""
Ferramentas de administração pela linha de comando.

    python gerenciar.py criar-usuario NOME [--papel admin|editor]
    python gerenciar.py trocar-senha NOME
    python gerenciar.py listar-usuarios
    python gerenciar.py backup
    python gerenciar.py restaurar CAMINHO_DO_BACKUP.zip
"""

import argparse
import getpass
import sys

from propagandas import create_app, db
from propagandas.auth import PAPEIS, ErroUsuario, criar_usuario, trocar_senha
from propagandas.backup import criar_backup, restaurar_backup


def pedir_senha():
    senha = getpass.getpass("Senha: ")
    if senha != getpass.getpass("Repita a senha: "):
        sys.exit("As senhas não conferem.")
    return senha


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Administração do Painel de Propagandas")
    comandos = parser.add_subparsers(dest="comando", required=True)

    criar = comandos.add_parser("criar-usuario", help="cria um usuário")
    criar.add_argument("usuario")
    criar.add_argument("--papel", choices=sorted(PAPEIS), default="admin")

    trocar = comandos.add_parser("trocar-senha", help="redefine a senha (útil se esqueceu)")
    trocar.add_argument("usuario")

    comandos.add_parser("listar-usuarios", help="mostra os usuários cadastrados")
    comandos.add_parser("backup", help="faz um backup agora")

    restaurar = comandos.add_parser("restaurar", help="restaura um backup (pare o servidor antes)")
    restaurar.add_argument("arquivo")

    args = parser.parse_args(argumentos)
    app = create_app()

    with app.app_context():
        conexao = db.obter()
        try:
            if args.comando == "criar-usuario":
                criar_usuario(conexao, args.usuario, pedir_senha(), args.papel)
                print(f"Usuário “{args.usuario}” criado ({PAPEIS[args.papel]}).")

            elif args.comando == "trocar-senha":
                linha = conexao.execute("SELECT id FROM usuarios WHERE usuario = ?", (args.usuario,)).fetchone()
                if linha is None:
                    sys.exit(f"Usuário “{args.usuario}” não encontrado.")
                trocar_senha(conexao, linha["id"], pedir_senha())
                print("Senha alterada.")

            elif args.comando == "listar-usuarios":
                for linha in conexao.execute("SELECT usuario, papel, criado_em FROM usuarios ORDER BY usuario"):
                    print(f"{linha['usuario']:<25} {PAPEIS[linha['papel']]:<15} desde {linha['criado_em']}")

            elif args.comando == "backup":
                print("Backup criado em:", criar_backup(app.config))

            elif args.comando == "restaurar":
                db.fechar()
                resposta = input("Isso substitui todas as propagandas atuais. Continuar? [s/N] ")
                if resposta.strip().lower() != "s":
                    sys.exit("Cancelado.")
                guardados = restaurar_backup(app.config, args.arquivo)
                print(f"Backup restaurado. Os dados anteriores foram guardados em: {guardados}")

        except (ErroUsuario, ValueError, FileNotFoundError) as erro:
            sys.exit(f"Erro: {erro}")


if __name__ == "__main__":
    main()
