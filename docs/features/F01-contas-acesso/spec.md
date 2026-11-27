# Spec — F01 Contas e acesso (W1)

- PRD: [docs/prd.md](../../prd.md), seções 3.1/3.2 (F01), 6 (F01-CA01…CA06), 7 (XF-01, XF-02) e 8.
- Branch: `feat/F01-contas-acesso`. Provedora: W0 (`dominio.Usuario`, `seed`), `concluida` na main.
- Plano: [plano.md](plano.md) · Contrato: [contrato.md](contrato.md)

## 1. Escopo

Entra: cadastro de participante, entrar, sair, guardas `organizador_requerido` e `participante_requerido`, esqueleto de `/organizador/`, bloco `#usuario-logado` e o teste que percorre as rotas de `/organizador/`.

Não entra: o modelo `Usuario`, a migration `dominio/0001` e a seed (são da W0 e não mudam; o F01-CA05 só verifica a seed); recuperação de senha, confirmação de e-mail, edição de perfil (fora de escopo, PRD seção 10); `/meus-ingressos/` (F03); lista de eventos em `/organizador/` (F02).

## 2. Domínio

### 2.1 Exceções — `dominio/excecoes.py` (novo)

Módulo único das exceções de domínio, que as features seguintes (`EventoNaoEncontrado`, `IngressosEsgotados` …) também usam.

```python
class ErroDeDominio(Exception): ...

class ValidacaoError(ErroDeDominio):
    """Dados de entrada inválidos. `erros` é dict campo -> lista de mensagens."""
    def __init__(self, erros: dict[str, list[str]]): ...

class EmailJaCadastrado(ValidacaoError):
    """E-mail já usado por outra conta (erros = {"email": [MSG_EMAIL_DUPLICADO]})."""
```

### 2.2 `cadastrar_participante(nome, email, senha) -> Usuario` — `dominio/servicos/contas.py`

1. Normaliza: `nome.strip()`; e-mail com `Usuario.normalizar_email` (strip + minúsculas, o mesmo que o `save()` e o login usam); a senha não é alterada.
2. Valida **todos** os campos e junta os erros num único `ValidacaoError` (o formulário mostra todos de uma vez). Mensagens, exatas:

| Campo | Situação | Mensagem |
|---|---|---|
| nome | vazio (ou só espaços) | "Informe o seu nome." |
| nome | mais de 150 caracteres | "O nome pode ter no máximo 150 caracteres." |
| email | vazio | "Informe o seu e-mail." |
| email | mal formado (`django.core.validators.validate_email`) ou mais de 254 caracteres | "Informe um e-mail válido." |
| email | já cadastrado (comparação já normalizada, então `Ana@X.com` = `ana@x.com`) | "Já existe uma conta com este e-mail." |
| senha | vazia | "Informe uma senha." |
| senha | menos de 8 caracteres | "A senha precisa ter pelo menos 8 caracteres." |
| senha | mais de 128 caracteres | "A senha pode ter no máximo 128 caracteres." |

   A checagem de duplicado só roda quando o e-mail é válido. Se só ela falhar, a exceção é `EmailJaCadastrado` (subclasse de `ValidacaoError`, então a view não precisa diferenciar).
3. Cria com `Usuario.objects.create_user(email, senha, nome=nome, papel=Usuario.Papel.PARTICIPANTE)` dentro de `transaction.atomic()`. O papel é fixo no código: o serviço não recebe papel nem flags, então nenhum dado de entrada cria organizador (R13). `create_user` chama `set_password` (PBKDF2, hasher padrão do Django; a coluna `password` guarda `pbkdf2_sha256$…`, nunca a senha).
4. Corrida de duas inscrições com o mesmo e-mail: a restrição `unique` do banco gera `IntegrityError`, que o serviço converte em `EmailJaCadastrado`.

As mensagens ficam como constantes no módulo (`MSG_NOME_VAZIO` …), e os testes importam as constantes e conferem o texto literal.

Por que a validação de formato fica no domínio e não no formulário: assim a regra e as mensagens existem num lugar só, e chamar o serviço direto (testes, futuras entradas) aplica as mesmas regras. O `AUTH_PASSWORD_VALIDATORS` do settings continua existindo para comandos do Django, mas o cadastro usa a regra própria acima, de mensagem fixa.

## 3. Web

### 3.1 Organização

- `web/views.py` vira o pacote `web/views/`: `__init__.py` (o `saude` e o `inicio` atuais, mais `falha_csrf`), `contas.py` (cadastro, entrar, sair) e `organizador.py` (esqueleto de `/organizador/`). A F02 acrescenta módulos próprios, o que reduz conflito na W4.
- `web/forms.py`: `CadastroForm` e `EntrarForm`, só para receber e reexibir os dados. Campos `CharField(required=False)`, sem validação própria; os erros vêm do domínio e a view os coloca no form com `form.add_error(campo, mensagem)`.
- `web/acesso.py`: guardas e funções de destino (3.5 e 3.3).
- Rotas em `web/urls.py`, nomes planos:

| Rota | Nome | Métodos | Guarda |
|---|---|---|---|
| `/contas/cadastro/` | `contas_cadastro` | GET, POST | — |
| `/contas/entrar/` | `contas_entrar` | GET, POST | — |
| `/contas/sair/` | `contas_sair` | POST (GET → 405) | — |
| `/organizador/` | `organizador_inicio` | GET | `organizador_requerido` |

- Settings: `LOGIN_URL = "/contas/entrar/"` e `CSRF_FAILURE_VIEW = "web.views.falha_csrf"` (falha de CSRF responde 403 com a mesma página genérica `403.html`, em vez da página padrão do Django). Nenhuma outra mudança de settings.

### 3.2 Cadastro — `/contas/cadastro/`

- `GET`: formulário `id="form-cadastro"`, `method="post"`, com `{% csrf_token %}` e os campos `nome` (texto, rótulo "Nome"), `email` (`type="email"`, rótulo "E-mail") e `senha` (`type="password"`, rótulo "Senha"). Botão "Criar conta". Link para `/contas/entrar/` ("Já tenho conta"). Carrega `next` num campo oculto quando veio na URL.
- `POST`: a view lê só `nome`, `email` e `senha` do form e chama `cadastrar_participante`. Qualquer outro campo enviado (`papel=organizador`, `is_staff=1`, `is_superuser=1`) é ignorado, porque o form não o declara e o serviço não o recebe (R13, F01-CA03).
  - Sucesso: `login(request, usuario)` (o Django troca a chave de sessão) e 302 para o destino (3.4). Sem `next`, o destino é `/` (a vitrine).
  - `ValidacaoError`: 200 com o formulário de novo, cada mensagem sob o seu campo (`<ul class="errorlist">` do Django), `nome` e `email` preenchidos com o que foi enviado e `senha` sempre vazia. Nada é gravado.
- Já autenticado: `GET` ou `POST` → 302 para o destino padrão do papel (3.4), sem criar conta.

### 3.3 Entrar — `/contas/entrar/`

- `GET`: formulário `id="form-entrar"` com `email` (`type="email"`), `senha` (`type="password"`), `next` oculto e `{% csrf_token %}`. Botão "Entrar". Link para `/contas/cadastro/` ("Criar conta").
- `POST`: `authenticate(request, username=email, password=senha)` do Django (o `ModelBackend` usa `get_by_natural_key`, que já normaliza o e-mail, então o login não diferencia maiúsculas). É autenticação de infraestrutura, não regra de negócio, por isso não há serviço de domínio para ela.
  - Sucesso: `login()` (nova chave de sessão) e 302 para o destino (3.4).
  - Falha, por qualquer motivo (e-mail inexistente, senha errada, conta inativa, campo vazio): 200, formulário reexibido com o e-mail preenchido e a mensagem única **"E-mail ou senha inválidos."** em `<p class="erro" id="erro-entrar">`. Nenhuma sessão é criada (o cliente só recebe o cookie `csrftoken`, nunca `sessionid`). A mensagem não diz qual dos dois está errado.
- Já autenticado: 302 para o destino (3.4), sem mostrar o formulário.

### 3.4 Destino depois de entrar (`?next=`)

`web.acesso.destino_depois_de_entrar(request, usuario)`:

1. Lê `next` (do `POST` no envio do formulário, do `GET` na exibição). Ele só é aceito se for **caminho interno**: começa com `/`, não começa com `//` nem com `/\`, não contém caracteres de controle e passa em `url_has_allowed_host_and_scheme(next, allowed_hosts=set())` (sem host nem esquema). Ex.: `/organizador/` e `/eventos/evt_ab12cd34/` são aceitos; `https://evil.example/`, `//evil.example/`, `/\evil.example`, `javascript:alert(1)` e `organizador/` são ignorados.
2. Sem `next` aceito, usa o **destino padrão**: organizador → `/organizador/`; participante → `/`.

A mesma função serve ao cadastro e ao entrar. O `next` aceito é repassado para o formulário (campo oculto) e para o link entre cadastro e entrar.

### 3.5 Sair — `/contas/sair/`

`require_POST`: `GET` responde 405 e não encerra a sessão. O `POST` passa pelo `CsrfViewMiddleware`: sem token válido, 403 (página genérica) e a sessão continua. Com token, `logout(request)` (apaga a sessão no banco e no cookie) e 302 para `/`. O botão "Sair" do `#usuario-logado` é um `<form method="post" action="/contas/sair/">` com `{% csrf_token %}`.

### 3.6 Guardas — `web/acesso.py`

Decoradores de view (função), com `functools.wraps`. Valem para todos os métodos HTTP e rodam antes da view, então uma requisição barrada nunca executa nada. A guarda é sempre o decorador **mais externo** (acima de `require_GET`/`require_POST`), para que um método não aceito também receba 302/403 antes de 405 e o teste de 4.2 valha para qualquer rota. Observação: um `POST` sem token CSRF é barrado antes, pelo `CsrfViewMiddleware` (403); a guarda decide os `POST` que trazem token válido.

**`organizador_requerido`**
- Visitante, em `GET`/`HEAD` → 302 para `/contas/entrar/?next=<caminho pedido>` (via `redirect_to_login(request.get_full_path(), LOGIN_URL)`; ex.: `/contas/entrar/?next=/organizador/`).
- Visitante, em outros métodos (`POST` …) → 302 para `/contas/entrar/` sem `next` (voltar a um endereço que só aceita POST daria 405 depois do login). A view não executa.
- Autenticado sem papel organizador (participante) → `PermissionDenied` → 403 com `403.html` ("Acesso negado"; nenhum dado da rota pedida). O handler padrão do Django já usa esse template.
- Organizador → a view executa.

**`participante_requerido`**
- Visitante → como acima: 302 para o login (com `next` em `GET`/`HEAD`, sem `next` nos outros métodos). É o comportamento que o XF-02 pede para `POST /eventos/<id>/comprar/`: o visitante vai ao login e nenhum ingresso é criado.
- **Organizador → 403 com a página genérica.** Comprar e ver "Meus ingressos" são ações do participante (R06, R09); a conta de organizador não compra. Sugestão para a F03 (não é decisão desta feature): o detalhe do evento pode mostrar para o visitante um link "Entre para comprar" para `/contas/entrar/?next=/eventos/<id>/`.
- Participante → a view executa.

Além dos decoradores, `web/acesso.py` tem `destino_padrao(usuario)` e `destino_depois_de_entrar(request, usuario)` (3.4).

### 3.7 `/organizador/` (esqueleto)

`GET` com `organizador_requerido`: 200 com `<section id="meus-eventos"><h2>Meus eventos</h2><p>Você ainda não tem eventos.</p></section>`. A F02 troca o conteúdo da seção pela lista dos eventos do organizador e cria as rotas `/organizador/eventos/…`, todas com `organizador_requerido` (o teste de 4.2 cobra isso).

### 3.8 Bloco `#usuario-logado` no `base.html`

O `<nav id="usuario-logado">` passa a incluir o parcial `web/_usuario_logado.html`, sem bloco sobrescrevível, para ser igual em todas as páginas:

| Quem | Conteúdo |
|---|---|
| Visitante | links "Entrar" (`/contas/entrar/`) e "Criar conta" (`/contas/cadastro/`) |
| Participante | `<span class="usuario-nome">` com o nome, link "Meus ingressos" (`href="/meus-ingressos/"`) e botão "Sair" |
| Organizador | nome, link "Área do organizador" (`/organizador/`) e botão "Sair"; **sem** "Meus ingressos" |

O nome passa pelo autoescape do template (nome com `<script>` aparece como texto).

**"Meus ingressos" até a F03.** O link aponta para o caminho fixo do PRD, `/meus-ingressos/`, escrito literalmente no template (não `{% url %}`, porque a rota ainda não existe e o `{% url %}` quebraria a página). Até a F03 registrar a rota, o link leva à página 404 genérica; isso é esperado e está no contrato como "fora deste contrato". A F03 só registra a rota com `participante_requerido`, sem mexer no parcial.

## 4. Testes

### 4.1 Unidade e integração (pytest, client do Django, Postgres do Compose)

- `dominio/tests/test_contas.py`: serviço (papel, hash, normalização, todas as mensagens da tabela 2.2, duplicado com caixa diferente, corrida simulada por `IntegrityError`).
- `web/tests/test_contas.py`: cadastro, entrar, sair, `next`, CSRF (`Client(enforce_csrf_checks=True)`), autenticado em entrar/cadastro.
- `web/tests/test_acesso.py`: guardas (com um `urls` de teste que registra views de exemplo para `participante_requerido`, porque nenhuma rota real usa essa guarda até a F03), `#usuario-logado` por papel e o teste de rotas de 4.2.

Os testes conferem os textos exatos das mensagens e os cabeçalhos `Location`.

### 4.2 Teste que percorre as rotas de `/organizador/`

`web/tests/test_acesso.py::test_rotas_do_organizador_barram_visitante_e_participante`:

1. Percorre `get_resolver().url_patterns` recursivamente (entrando nos `include`), montando o caminho completo de cada `URLPattern` a partir de `str(padrao.pattern)`.
2. Fica com os caminhos que começam com `organizador/`. Se algum for `re_path` (sem conversores tipados), o teste falha com a mensagem "use path() nas rotas do organizador".
3. Preenche cada parâmetro `<conversor:nome>` com um valor fictício pelo tipo do conversor (`int` → `999999`, `str`/`slug` → `"inexistente"`, `uuid` → um UUID fixo, `path` → `"inexistente"`), passando por `conversor.to_url()`.
4. Para cada URL: visitante em `GET` → 302 com `Location` começando por `/contas/entrar/`; visitante em `POST` → 302 para `/contas/entrar/`; participante em `GET` e em `POST` → 403. Também exige que a lista tenha pelo menos `/organizador/`, para o teste nunca passar vazio.

Como os valores são fictícios, o teste não depende de dados: a guarda responde antes de a view procurar qualquer evento. As rotas que a F02 e as seguintes criarem sob `/organizador/` entram nele sozinhas.

## 5. Como a F01 permite XF-01 e XF-02

- **XF-01 [F01→F02]**: o participante recebe 403 em qualquer rota `/organizador/…` em `GET` e em `POST` (a view nem executa, então o `POST` não cria evento), e o visitante vai para o login sem receber dados. A F02 só precisa decorar as views com `organizador_requerido`; o teste 4.2 falha se esquecer.
- **XF-02 [F01→F03]**: uma conta criada pelo cadastro já sai autenticada como participante; `participante_requerido` barra o visitante (302 para o login, view não executa) e o organizador (403); o link "Meus ingressos" já aparece para o participante em `#usuario-logado`.

## 6. Riscos e decisões menores

- **Enumeração de contas**: o cadastro diz "Já existe uma conta com este e-mail.", o que revela que o e-mail existe. Aceito no MVP (F01-CA02 pede o erro); o entrar não revela nada.
- **Força bruta no entrar**: sem limite de tentativas (fora de escopo; PRD seção 10 exclui limite de taxa).
- **Formulário inválido responde 200**, convenção do Django para reexibir formulário; os critérios conferem a mensagem e a contagem de usuários.
- **Mensagens flash**: não há, para não somar textos verificáveis; o sinal de sucesso é o redirecionamento e o nome em `#usuario-logado`.
