"""Numeros por extenso em portugues, nos dois sentidos.

Existe para permitir comandos com parametro -- "servo trinta graus",
"piscar led cinco vezes" -- em vez de so frases fixas.

A conversao inversa (int -> palavras) e usada para montar a gramatica do Vosk:
o decodificador precisa ter "trinta" no vocabulario para conseguir reconhecer.
"""

from __future__ import annotations

from ..utils import tokens as _tokens

UNIDADES = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3,
    "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9,
}

ESPECIAIS = {
    "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14,
    "quatorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17,
    "dezoito": 18, "dezenove": 19,
}

DEZENAS = {
    "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50,
    "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90,
}

CENTENAS = {
    "cem": 100, "cento": 100, "duzentos": 200, "trezentos": 300,
}

PALAVRAS_NUMERICAS = {**UNIDADES, **ESPECIAIS, **DEZENAS, **CENTENAS}

#: Token que substitui o numero no texto normalizado, para o roteador casar
#: "servo numero graus" tanto com "servo trinta graus" quanto com "servo 30 graus".
PLACEHOLDER = "numero"


def _valor_do_token(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return PALAVRAS_NUMERICAS.get(token)


def extract_number(text: str) -> int | None:
    """Primeiro numero encontrado no texto, por extenso ou em digitos."""
    _, valores = replace_numbers(text)
    return valores[0] if valores else None


def replace_numbers(text: str) -> tuple[list[str], list[int]]:
    """Troca os numeros do texto pelo placeholder e devolve os valores.

    >>> replace_numbers("servo trinta e cinco graus")
    (['servo', 'numero', 'graus'], [35])
    """
    palavras = _tokens(text)
    saida: list[str] = []
    valores: list[int] = []

    i = 0
    while i < len(palavras):
        valor = _valor_do_token(palavras[i])
        if valor is None:
            saida.append(palavras[i])
            i += 1
            continue

        total = valor
        i += 1
        # Compoe "cento e oitenta", "trinta e cinco", "cento e vinte e um".
        while i < len(palavras):
            if palavras[i] == "e" and i + 1 < len(palavras):
                proximo = _valor_do_token(palavras[i + 1])
                # So compoe se o proximo for menor: evita juntar
                # "cinco e trinta" (que sao dois numeros distintos).
                if proximo is not None and proximo < total:
                    total += proximo
                    i += 2
                    continue
            break

        saida.append(PLACEHOLDER)
        valores.append(total)

    return saida, valores


def number_to_words(value: int) -> str:
    """Inverso de `extract_number`, para montar a gramatica do Vosk."""
    if value < 0:
        return ""

    inverso_unidades = {v: k for k, v in UNIDADES.items() if k not in {"uma", "duas"}}
    inverso_especiais = {v: k for k, v in ESPECIAIS.items() if k != "quatorze"}
    inverso_dezenas = {v: k for k, v in DEZENAS.items()}

    if value in inverso_especiais:
        return inverso_especiais[value]
    if value < 10:
        return inverso_unidades[value]
    if value < 100:
        dezena, unidade = divmod(value, 10)
        base = inverso_dezenas[dezena * 10]
        return base if unidade == 0 else f"{base} e {inverso_unidades[unidade]}"
    if value == 100:
        return "cem"
    if value < 200:
        resto = value - 100
        return "cento" if resto == 0 else f"cento e {number_to_words(resto)}"

    centena, resto = divmod(value, 100)
    base = {2: "duzentos", 3: "trezentos"}.get(centena)
    if base is None:
        return str(value)
    return base if resto == 0 else f"{base} e {number_to_words(resto)}"
