"""
prepare_build.py — Prepara a chave Gemini gerenciada antes de rodar o PyInstaller.

Uso:
    python prepare_build.py AIzaSy...suaChaveAqui

O script gera utils/managed_key.py com a chave codificada via XOR+base64.
Esse arquivo é listado no .gitignore e NUNCA sobe para o repositório.

Depois de rodar este script, execute:
    pyinstaller BTExtract.spec --noconfirm
ou simplesmente:
    build_installer.bat
"""
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Uso: python prepare_build.py SUA_GEMINI_API_KEY")
        print("Exemplo: python prepare_build.py AIzaSyXXXXXXXXXXXXXXXXXXXXXXXX")
        sys.exit(1)

    plain_key = sys.argv[1].strip()
    if not plain_key.startswith("AIza"):
        print(f"[AVISO] A chave nao parece ser uma Gemini API Key valida (esperado comecar com 'AIza').")
        confirm = input("Continuar mesmo assim? (s/N) ").strip().lower()
        if confirm != "s":
            sys.exit(0)

    # Importa o encoder
    sys.path.insert(0, str(Path(__file__).parent))
    from utils.key_manager import encode_key

    encoded = encode_key(plain_key)

    # Gera utils/managed_key.py
    out_path = Path(__file__).parent / "utils" / "managed_key.py"
    out_path.write_text(
        f'# AUTO-GERADO por prepare_build.py — NAO COMMITAR\n'
        f'# Remova este arquivo para voltar ao modo "usuario configura propria chave"\n'
        f'ENCODED_KEY = "{encoded}"\n',
        encoding="utf-8",
    )

    print(f"[OK] utils/managed_key.py gerado com sucesso.")
    print(f"     Chave original : {plain_key[:8]}...{plain_key[-4:]} ({len(plain_key)} chars)")
    print(f"     Chave codificada: {encoded[:20]}... ({len(encoded)} chars)")
    print()
    print("Proximo passo: execute build_installer.bat")


if __name__ == "__main__":
    main()
