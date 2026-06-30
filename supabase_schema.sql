-- ============================================================
-- BTExtract — Schema para Supabase (PostgreSQL)
-- Execute ONCE no SQL Editor do Supabase Dashboard
-- ============================================================

-- Empresas cadastradas no sistema
CREATE TABLE IF NOT EXISTS empresas (
    id           TEXT PRIMARY KEY,
    razao_social TEXT NOT NULL,
    cnpj         TEXT,
    email_admin  TEXT NOT NULL,
    ativo        INTEGER NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by   TEXT
);

-- Usuários (todos os roles: superadmin, admin, user)
CREATE TABLE IF NOT EXISTS usuarios (
    id              TEXT PRIMARY KEY,
    empresa_id      TEXT NOT NULL,
    nome            TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    senha_hash      TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user',
    ativo           INTEGER NOT NULL DEFAULT 1,
    lgpd_consent_at TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_usuarios_empresa ON usuarios(empresa_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_email   ON usuarios(email);

-- Audit log — nunca apagar; anonimizar apenas PII
CREATE TABLE IF NOT EXISTS audit_log (
    id         SERIAL PRIMARY KEY,
    usuario_id TEXT,
    empresa_id TEXT,
    acao       TEXT NOT NULL,
    detalhes   TEXT,
    ip         TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_empresa ON audit_log(empresa_id);
CREATE INDEX IF NOT EXISTS idx_audit_usuario ON audit_log(usuario_id);

-- Sessões de extração (histórico por empresa)
CREATE TABLE IF NOT EXISTS sessoes (
    id           SERIAL PRIMARY KEY,
    empresa_id   TEXT NOT NULL,
    usuario_id   TEXT NOT NULL,
    tema         TEXT DEFAULT 'Triagem Geral',
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    results_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessoes_empresa ON sessoes(empresa_id);

-- Configurações globais (Gmail, Gemini, etc.)
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Comentários de recrutadores por arquivo
CREATE TABLE IF NOT EXISTS comments (
    filename   TEXT PRIMARY KEY,
    comment    TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Empresa-sistema para o superadmin (id fixo)
INSERT INTO empresas (id, razao_social, email_admin)
VALUES ('00000000-0000-0000-0000-000000000000', '[SISTEMA] Bertoi Informatica', 'sistema@bertoi.com')
ON CONFLICT (id) DO NOTHING;
