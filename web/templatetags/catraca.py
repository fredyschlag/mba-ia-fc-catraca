"""Filtros de apresentação usados pelas telas (sem regra de negócio)."""

from django import template

register = template.Library()


@register.filter
def reais(centavos):
    """Centavos inteiros → "R$ 1.234,56"."""
    if centavos is None or centavos == "":
        return ""
    centavos = int(centavos)
    sinal = "-" if centavos < 0 else ""
    inteiro, resto = divmod(abs(centavos), 100)
    milhares = f"{inteiro:,}".replace(",", ".")
    return f"R$ {sinal}{milhares},{resto:02d}"
