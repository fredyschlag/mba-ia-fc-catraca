# Plano — F06 Painel

Spec: [spec.md](spec.md) · Contrato: [contrato.md](contrato.md). Branch `feat/F06-painel`, porta 8000.

Cada etapa termina com `./scripts/gates.sh` em código 0, entra com os seus testes e vira um commit com push. Comandos Python só por `./scripts/dev.sh`. Sem migration nova.

| # | Etapa | Arquivos | Testes que entram junto |
|---|---|---|---|
| 1 | `Painel` e `painel_do_evento` | `dominio/servicos/painel.py` | `dominio/tests/test_painel.py`: `test_painel_de_evento_sem_ingressos`, `test_painel_conta_cada_status_pela_definicao`, `test_check_ins_so_de_confirmados`, `test_receita_soma_o_preco_gravado_de_cada_confirmado`, `test_receita_ignora_pendentes_recusados_cancelados_e_estornados`, `test_vitrine_e_api_contam_igual`, `test_vagas_disponiveis_segue_r05_e_zera_em_cancelado`, `test_painel_usa_uma_consulta_agregada` (exatamente 2 consultas: os agregados e as vagas de R05) |
| 2 | Bloco `#painel` na gestão (template tag e parcial) | `web/templatetags/painel.py`, `web/templates/web/organizador/gestao/_painel.html`, `web/templates/web/organizador/gestao/_painel_conteudo.html` | `web/tests/test_painel.py`: `test_bloco_painel_na_gestao_com_rotulos_e_metricas`, `test_receita_no_formato_reais`, `test_recarregar_mostra_estado_atual`, `test_outro_organizador_nao_ve_o_painel` |
| 3 | Verificação no ambiente | — | do zero; todos os itens do [contrato](contrato.md) (inclusive rajada pela API, cartões lentos e check-in); `./scripts/down.sh` |
| 4 | Pedir avaliação | `estado.json` | F06 em `em_avaliacao`, commit, push, árvore limpa; avaliação por subagente novo |
