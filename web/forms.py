"""Formulários das telas de contas.

Só recebem e reexibem os dados: as regras e as mensagens de validação ficam no domínio
(`dominio.servicos.contas`). A senha nunca é reexibida.
"""

from django import forms


class CadastroForm(forms.Form):
    nome = forms.CharField(label="Nome", required=False, strip=False)
    email = forms.CharField(label="E-mail", required=False, strip=False, widget=forms.EmailInput)
    senha = forms.CharField(
        label="Senha",
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
    )


class EntrarForm(forms.Form):
    email = forms.CharField(label="E-mail", required=False, strip=False, widget=forms.EmailInput)
    senha = forms.CharField(
        label="Senha",
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
    )
