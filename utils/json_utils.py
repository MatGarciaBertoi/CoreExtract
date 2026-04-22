"""
Utilitários de extração robusta de JSON para respostas de modelos de linguagem.
Lida com respostas truncadas (finish_reason=MAX_TOKENS), markdown e texto extra.
"""
import json
import re


def _repair_truncated_json(text: str) -> str:
    """
    Tenta fechar um JSON truncado adicionando os fechamentos de chaves/arrays
    que estão faltando.
    """
    # Encontra o início do JSON
    start = text.find("{")
    if start == -1:
        return text
    fragment = text[start:]

    # Conta profundidade de chaves e arrays para fechar o que está aberto
    depth_brace   = 0
    depth_bracket = 0
    in_string     = False
    escape_next   = False

    for ch in fragment:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1

    # Se estava no meio de uma string, fecha ela
    closing = ""
    if in_string:
        closing += '"'

    # Fecha arrays e chaves abertas (da mais interna para a mais externa)
    closing += "]" * max(0, depth_bracket)
    closing += "}" * max(0, depth_brace)

    return fragment + closing


def extract_json(raw: str) -> dict:
    """
    Tenta extrair um objeto JSON da resposta do modelo com 4 estratégias:

    1. Parse direto (caminho feliz)
    2. Remove blocos de código markdown  ```json ... ```
    3. Extrai o maior bloco { ... } completo por balanceamento de chaves
    4. Repara JSON truncado (finish_reason=MAX_TOKENS) fechando chaves abertas
    """
    text = raw.strip()

    # 1. Parse direto
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Remove markdown code fences
    md = re.search(r"```(?:json)?\s*([\s\S]+?)```", text, re.IGNORECASE)
    if md:
        try:
            return json.loads(md.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Extrai o maior bloco { ... } completo por balanceamento de chaves
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start: i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    # 4. Repara JSON truncado — fecha chaves/arrays abertos
    try:
        repaired = _repair_truncated_json(text)
        if repaired != text:
            return json.loads(repaired)
    except (json.JSONDecodeError, Exception):
        pass

    raise ValueError(
        f"Modelo retornou resposta não-JSON (primeiros 300 chars): {raw[:300]!r}"
    )
