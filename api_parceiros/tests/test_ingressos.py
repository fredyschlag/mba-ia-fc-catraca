import json

import pytest
from django.test import Client
from django.utils import timezone

from api_parceiros.tests.conftest import corpo_compra, publicado, url_compra, url_ingresso
from dominio.models import Ingresso

pytestmark = pytest.mark.django_db


def _comprar_pela_api(api, evento, cartao="4000000000000001"):
    resposta = api.post(url_compra(evento.id_publico), corpo_compra(cartao=cartao))
    assert resposta.status_code == 202
    return json.loads(resposta.content)


def test_consulta_tem_exatamente_os_cinco_campos(api, organizador):
    evento = publicado(organizador)
    compra = _comprar_pela_api(api, evento)
    resposta = api.get(url_ingresso(compra["ticketId"]))
    assert resposta.status_code == 200
    assert resposta["Content-Type"] == "application/json"
    assert resposta.content.decode() == (
        f'{{"ticketId":"{compra["ticketId"]}","code":"{compra["code"]}",'
        f'"eventId":"{evento.id_publico}","status":"pending","checkedIn":false}}'
    )


@pytest.mark.parametrize("status", ["pending", "confirmed", "declined", "cancelled", "refunded"])
def test_consulta_mostra_cada_status(api, organizador, status):
    compra = _comprar_pela_api(api, publicado(organizador))
    Ingresso.objects.filter(id_publico=compra["ticketId"]).update(status=status)
    dados = json.loads(api.get(url_ingresso(compra["ticketId"])).content)
    assert dados["status"] == status
    assert dados["checkedIn"] is False


def test_checked_in_vem_de_check_in_em(api, organizador):
    compra = _comprar_pela_api(api, publicado(organizador))
    Ingresso.objects.filter(id_publico=compra["ticketId"]).update(
        status=Ingresso.Status.CONFIRMADO, check_in_em=timezone.now()
    )
    dados = json.loads(api.get(url_ingresso(compra["ticketId"])).content)
    assert dados["checkedIn"] is True
    assert dados["status"] == "confirmed"


def test_ingresso_da_vitrine_e_consultavel_com_o_mesmo_code(api, organizador, participante):
    evento = publicado(organizador)
    vitrine = Client()
    vitrine.force_login(participante)
    vitrine.post(f"/eventos/{evento.id_publico}/comprar/", {"cartao": "4000000000000001"})
    ingresso = Ingresso.objects.get(comprador=participante)
    assert ingresso.canal == Ingresso.Canal.VITRINE
    meus = vitrine.get("/meus-ingressos/").content.decode()
    assert f'data-campo="codigo">{ingresso.codigo}<' in meus
    dados = json.loads(api.get(url_ingresso(ingresso.id_publico)).content)
    assert dados == {
        "ticketId": ingresso.id_publico,
        "code": ingresso.codigo,
        "eventId": evento.id_publico,
        "status": "pending",
        "checkedIn": False,
    }


def test_ingresso_inexistente_responde_404(api, organizador):
    compra = _comprar_pela_api(api, publicado(organizador))
    for ticket_id in ("tkt_naoexiste", compra["code"], compra["ticketId"].upper(), "x"):
        resposta = api.get(url_ingresso(ticket_id))
        assert resposta.status_code == 404
        assert resposta.content == b'{"error":"ticket_not_found"}'
        assert resposta["Content-Type"] == "application/json"
