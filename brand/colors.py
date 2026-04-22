"""
Paleta de cores e tokens visuais do CoreExtract.
Usados nos templates HTML de e-mail e frontend.
"""

NAVY    = "#0D1B2A"
BLUE    = "#1A6BFF"
CYAN    = "#00C8FF"
EMERALD = "#00D68F"
AMBER   = "#FFB830"
CORAL   = "#FF5757"
SLATE   = "#F4F7FF"
GRAY    = "#6B7A99"
WHITE   = "#FFFFFF"
DARK    = "#1A1A2E"

GRADIENT_PRIMARY = "linear-gradient(135deg, #0D1B2A 0%, #1A3A6B 50%, #1A6BFF 100%)"
GRADIENT_ACCENT  = "linear-gradient(90deg, #1A6BFF 0%, #00C8FF 100%)"
GRADIENT_SUCCESS = "linear-gradient(90deg, #00C8FF 0%, #00D68F 100%)"

# Mapeamento de senioridade → cor de badge
SENIORITY_COLORS: dict[str, str] = {
    "Júnior":      AMBER,
    "Pleno":       BLUE,
    "Sênior":      EMERALD,
    "Especialista": CYAN,
    "Indefinido":  GRAY,
}
