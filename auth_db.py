"""
auth_db.py — dispatcher automático entre backends SQLite e PostgreSQL.

- Se DATABASE_URL estiver definida (Vercel + Supabase) → usa _auth_db_pg
- Caso contrário (Oracle VM / local) → usa _auth_db_sqlite (implementação original)

Todos os módulos externos continuam importando apenas `auth_db` normalmente.
"""
import os as _os

if _os.environ.get("DATABASE_URL"):
    from _auth_db_pg import *  # noqa: F401, F403
    from _auth_db_pg import (  # noqa: F401
        SYSTEM_EMPRESA_ID,
        criar_empresa,
        get_empresa,
        listar_empresas,
        desativar_empresa,
        reativar_empresa,
        atualizar_empresa,
        ensure_sistema_empresa,
        criar_usuario,
        get_usuario_por_email,
        get_usuario,
        listar_usuarios_empresa,
        desativar_usuario,
        reativar_usuario,
        atualizar_usuario,
        alterar_senha_hash,
        apagar_dados_usuario,
        email_existe,
        salvar_sessao,
        get_ultima_sessao,
        listar_sessoes,
        get_sessao,
        log_acao,
        listar_audit,
    )
else:
    from _auth_db_sqlite import *  # noqa: F401, F403
    from _auth_db_sqlite import (  # noqa: F401
        SYSTEM_EMPRESA_ID,
        criar_empresa,
        get_empresa,
        listar_empresas,
        desativar_empresa,
        reativar_empresa,
        atualizar_empresa,
        criar_usuario,
        get_usuario_por_email,
        get_usuario,
        listar_usuarios_empresa,
        desativar_usuario,
        reativar_usuario,
        atualizar_usuario,
        apagar_dados_usuario,
        email_existe,
        salvar_sessao,
        get_ultima_sessao,
        listar_sessoes,
        get_sessao,
        log_acao,
        listar_audit,
    )

    def ensure_sistema_empresa(email_admin: str) -> None:
        """Garante que a empresa-sistema existe (SQLite: INSERT OR IGNORE)."""
        import sqlite3
        from utils.paths import DB_PATH
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute(
                "INSERT OR IGNORE INTO empresas (id, razao_social, email_admin) "
                "VALUES (?, '[SISTEMA] Bertoi Informatica', ?)",
                (SYSTEM_EMPRESA_ID, email_admin),
            )
            conn.commit()
        finally:
            conn.close()

    def alterar_senha_hash(user_id: str, new_hash: str) -> bool:
        """Atualiza senha_hash de um usuário (SQLite)."""
        import sqlite3
        from utils.paths import DB_PATH
        conn = sqlite3.connect(str(DB_PATH))
        try:
            cur = conn.execute(
                "UPDATE usuarios SET senha_hash = ? WHERE id = ?", (new_hash, user_id)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
