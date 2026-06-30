"""
settings_db.py — dispatcher automático entre backends SQLite e PostgreSQL.

- Se DATABASE_URL estiver definida (Vercel + Supabase) → usa _settings_db_pg
- Caso contrário (Oracle VM / local) → usa _settings_db_sqlite (original)

Todos os módulos externos continuam importando apenas `settings_db` normalmente.
"""
import os as _os

if _os.environ.get("DATABASE_URL"):
    from _settings_db_pg import *  # noqa: F401, F403
    from _settings_db_pg import (  # noqa: F401
        get,
        set,
        get_all,
        set_many,
        save_comment,
        get_comment,
        delete_comments_for_files,
        get_comments_for_files,
    )
else:
    from _settings_db_sqlite import *  # noqa: F401, F403
    from _settings_db_sqlite import (  # noqa: F401
        get,
        set,
        get_all,
        set_many,
        save_comment,
        get_comment,
        delete_comments_for_files,
        get_comments_for_files,
    )
