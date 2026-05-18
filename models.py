"""
Modelos Pydantic do BTExtract.
Versão enriquecida com todos os campos que o Gemini pode extrair
e campos de metadados de processamento.
Inclui modelos de autenticação multi-tenant (JWT, empresas, usuários).
"""
from typing import Literal, Optional
from pydantic import BaseModel, field_validator, model_validator


# =========================================================================== #
#  SUBMODELOS — blocos reutilizáveis                                            #
# =========================================================================== #

class Contato(BaseModel):
    email:    Optional[str] = None
    telefone: Optional[str] = None
    linkedin: Optional[str] = None
    github:   Optional[str] = None
    portfolio: Optional[str] = None
    cidade:   Optional[str] = None
    estado:   Optional[str] = None
    pais:     Optional[str] = "Brasil"


class Habilidades(BaseModel):
    """Skills categorizadas para facilitar triagem por tipo."""
    tecnicas:       list[str] = []   # linguagens, frameworks, ferramentas
    comportamentais: list[str] = []  # soft skills
    ferramentas:    list[str] = []   # IDEs, plataformas, SaaS
    idiomas:        list[str] = []   # idiomas com proficiência (ex: "Inglês — Avançado")


class Experiencia(BaseModel):
    cargo:        Optional[str] = None
    empresa:      Optional[str] = None
    periodo:      Optional[str] = None   # ex: "Jan/2022 – Atual"
    descricao:    Optional[str] = None   # resumo das responsabilidades
    conquistas:   list[str] = []         # realizações quantificadas


class Formacao(BaseModel):
    curso:        Optional[str] = None
    instituicao:  Optional[str] = None
    nivel:        Optional[str] = None   # Graduação, MBA, Pós-Graduação, Técnico...
    ano_conclusao: Optional[str] = None
    em_andamento: bool = False


class Certificacao(BaseModel):
    nome:         Optional[str] = None
    emissor:      Optional[str] = None   # ex: AWS, Google, Microsoft
    ano:          Optional[str] = None
    credencial_id: Optional[str] = None


class ScoreAnalise(BaseModel):
    """
    Scores base extraídos do currículo (0–100).
    Quando há análise de fit, o score_geral é substituído pelo fit.score_fit.
    """
    experiencia_relevante: int = 0    # profundidade e volume de experiência
    formacao_academica:    int = 0    # nível e qualidade da formação
    score_geral:           int = 0    # calculado (ver compute_score_geral)

    @field_validator(
        "experiencia_relevante", "formacao_academica", "score_geral",
        mode="before",
    )
    @classmethod
    def clamp_score(cls, v) -> int:
        try:
            return max(0, min(100, int(v)))
        except (TypeError, ValueError):
            return 0


class FitAnalise(BaseModel):
    """
    Análise de aderência quando uma descrição de vaga é fornecida.
    Só é preenchida se o campo job_description for enviado na requisição.
    Todos os scores derivam da comparação candidato × vaga.
    """
    score_fit:         int = 0          # 0–100 aderência geral à vaga
    score_experiencia: int = 0          # 0–100 match da experiência com a vaga
    score_formacao:    int = 0          # 0–100 match da formação com a vaga
    score_tecnico:     int = 0          # 0–100 match das habilidades técnicas com a vaga
    pontos_fortes:     list[str] = []   # por que o candidato se encaixa
    lacunas:           list[str] = []   # o que está faltando
    recomendacao:      Optional[Literal["Avançar", "Em análise", "Não recomendado"]] = None

    @field_validator("score_fit", "score_experiencia", "score_formacao", "score_tecnico", mode="before")
    @classmethod
    def clamp_fit_score(cls, v) -> int:
        try:
            return max(0, min(100, int(v)))
        except (TypeError, ValueError):
            return 0


# =========================================================================== #
#  MODELO PRINCIPAL DE SAÍDA                                                    #
# =========================================================================== #

class ResumeOutput(BaseModel):
    # Dados pessoais
    nome:                       Optional[str] = None
    contato:                    Optional[Contato] = None

    # Perfil profissional
    resumo_profissional:        Optional[str] = None
    nivel_senioridade:          Optional[str] = "Indefinido"
    anos_experiencia_estimados: Optional[float] = None   # aceita float do modelo (ex: 0.75, 1.5)
    area_atuacao:               Optional[str] = None   # ex: "Engenharia de Software"

    # Competências
    habilidades:                Habilidades = Habilidades()

    # Histórico
    experiencias:               list[Experiencia] = []   # mais recente primeiro
    formacoes:                  list[Formacao] = []
    certificacoes:              list[Certificacao] = []

    # Análise de qualidade
    scores:                     ScoreAnalise = ScoreAnalise()
    fit:                        Optional[FitAnalise] = None  # só se job_description enviado

    # Metadados de extração
    confianca_extracao:         Optional[str] = None  # "Alta" | "Média" | "Baixa"
    observacoes_ia:             Optional[str] = None  # alertas do modelo (ex: "currículo incompleto")

    @field_validator("nivel_senioridade")
    @classmethod
    def validate_senioridade(cls, v: Optional[str]) -> str:
        allowed = {"Júnior", "Pleno", "Sênior", "Especialista", "Indefinido"}
        return v if v in allowed else "Indefinido"

    @model_validator(mode="after")
    def compute_score_geral(self) -> "ResumeOutput":
        s = self.scores
        # Quando há fit, score_geral = fit.score_fit (análise real contra a vaga)
        if self.fit and self.fit.score_fit > 0:
            s.score_geral = self.fit.score_fit
        elif s.score_geral == 0:
            # Sem vaga: ponderação experiência (70%) + formação (30%)
            s.score_geral = int(
                s.experiencia_relevante * 0.70
                + s.formacao_academica   * 0.30
            )
        return self


# =========================================================================== #
#  MODELOS DE REQUISIÇÃO                                                        #
# =========================================================================== #

class EmailRequest(BaseModel):
    destinatario:        str
    tema:                Optional[str] = "Triagem Geral"
    job_description:     Optional[str] = None   # JD para análise de fit
    contexto_adicional:  Optional[str] = None
    nome_recrutador:     Optional[str] = None
    empresa_recrutadora: Optional[str] = None


# =========================================================================== #
#  MODELO DE RESULTADO POR ARQUIVO                                              #
# =========================================================================== #

class ProcessingResult(BaseModel):
    filename:      str
    status:        Literal["ok", "error"]
    resume:        Optional[ResumeOutput] = None
    error:         Optional[str] = None
    meta:          Optional[dict] = None   # RequestContext.to_response_meta()


# =========================================================================== #
#  MODELOS DE AUTENTICAÇÃO                                                      #
# =========================================================================== #

class LoginPayload(BaseModel):
    """Payload do endpoint POST /auth/login."""
    email: str
    senha: str


class Token(BaseModel):
    """Resposta do login bem-sucedido."""
    access_token: str
    token_type:   str = "bearer"
    role:         str
    nome:         str
    empresa_id:   str
    empresa_nome: Optional[str] = None


class EmpresaCreate(BaseModel):
    """
    Payload para criação de empresa (superadmin only).
    Cria a empresa + o admin dela em uma única operação.
    """
    razao_social: str
    cnpj:         Optional[str] = None
    email_admin:  str           # e-mail corporativo do primeiro admin
    nome_admin:   str           # nome do admin
    senha_admin:  str           # senha temporária (admin deve trocar depois)


class UserCreate(BaseModel):
    """Payload para criação de usuário (empresa admin only)."""
    nome:  str
    email: str
    senha: str
    role:  Literal["admin", "user"] = "user"


class UserResponse(BaseModel):
    """Resposta segura de usuário (sem senha_hash)."""
    id:             str
    empresa_id:     str
    nome:           str
    email:          str
    role:           str
    ativo:          bool
    lgpd_consent_at: Optional[str] = None
    created_at:     Optional[str] = None


class EmpresaResponse(BaseModel):
    """Resposta de empresa (para listagem no painel admin)."""
    id:           str
    razao_social: str
    cnpj:         Optional[str] = None
    email_admin:  str
    ativo:        bool
    created_at:   Optional[str] = None
    total_usuarios: Optional[int] = None


class AlterarSenhaPayload(BaseModel):
    """Payload para alteração de senha do próprio usuário."""
    senha_atual: str
    nova_senha:  str
