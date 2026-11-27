"""Bloco do painel na gestão (F06): a tag só chama o domínio e entrega o `Painel` ao template."""

from django import template

from dominio.servicos.painel import painel_do_evento

register = template.Library()


@register.inclusion_tag("web/organizador/gestao/_painel_conteudo.html")
def bloco_painel(evento):
    return {"painel": painel_do_evento(evento)}
