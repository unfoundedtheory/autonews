"""Configurable JSON-output AI gateway. No paid fallback without explicit opt-in.

Supported: Gemini, DeepSeek, OpenAI, Anthropic, OpenRouter, Groq, Mistral,
Together and local Ollama. Hostnames are fixed: requests cannot select arbitrary URLs.
Providers may change model availability: select an existing model in environment.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
import httpx


@dataclass(frozen=True)
class Provider:
    name: str
    key_env: str | None
    model_env: str
    default_model: str
    kind: str
    url: str
    possibly_billable: bool = True


PROVIDERS: dict[str, Provider] = {
    'gemini': Provider('gemini', 'GEMINI_API_KEY', 'GEMINI_MODEL', 'gemini-2.5-flash-lite',
                       'gemini', 'https://generativelanguage.googleapis.com/v1beta/models', False),
    'deepseek': Provider('deepseek', 'DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', 'deepseek-flash',
                         'openai', 'https://api.deepseek.com/chat/completions'),
    'openai': Provider('openai', 'OPENAI_API_KEY', 'OPENAI_MODEL', 'gpt-4.1-mini',
                      'openai', 'https://api.openai.com/v1/chat/completions'),
    'anthropic': Provider('anthropic', 'ANTHROPIC_API_KEY', 'ANTHROPIC_MODEL', 'claude-haiku-4-5',
                         'anthropic', 'https://api.anthropic.com/v1/messages'),
    'openrouter': Provider('openrouter', 'OPENROUTER_API_KEY', 'OPENROUTER_MODEL', 'openai/gpt-4.1-mini',
                          'openai', 'https://openrouter.ai/api/v1/chat/completions'),
    'groq': Provider('groq', 'GROQ_API_KEY', 'GROQ_MODEL', 'llama-3.3-70b-versatile',
                     'openai', 'https://api.groq.com/openai/v1/chat/completions'),
    'mistral': Provider('mistral', 'MISTRAL_API_KEY', 'MISTRAL_MODEL', 'mistral-small-latest',
                        'openai', 'https://api.mistral.ai/v1/chat/completions'),
    'together': Provider('together', 'TOGETHER_API_KEY', 'TOGETHER_MODEL', 'meta-llama/Llama-3.3-70B-Instruct-Turbo',
                         'openai', 'https://api.together.xyz/v1/chat/completions'),
    'ollama': Provider('ollama', None, 'OLLAMA_MODEL', 'qwen2.5:7b',
                       'ollama', 'http://127.0.0.1:11434/api/generate', False),
}


class InvalidProviderResponse(ValueError):
    pass


def configured_providers() -> list[str]:
    """Show provider connectivity only, never expose API key values."""
    return [name for name, spec in PROVIDERS.items()
            if (spec.key_env and os.getenv(spec.key_env)) or name == 'ollama']


def _decode_json(text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise InvalidProviderResponse('AI tidak mengembalikan teks JSON')
    try:
        value = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise InvalidProviderResponse('AI menghasilkan JSON tidak valid') from exc
    if not isinstance(value, dict):
        raise InvalidProviderResponse('Respons AI harus berupa JSON object')
    return value


def _model_for(spec: Provider, *, role: str, model: str | None) -> str:
    if model:
        return model
    task_model = os.getenv('AI_' + role.upper() + '_MODEL', '').strip()
    return task_model or os.getenv(spec.model_env, spec.default_model).strip() or spec.default_model


def _single(spec: Provider, system: str, data: dict, *, temperature: float,
            model: str | None, role: str, transport=None) -> dict:
    selected = _model_for(spec, role=role, model=model)
    secret = (os.getenv(spec.key_env, '') if spec.key_env else '').strip()
    if spec.key_env and not secret:
        raise RuntimeError(f'{spec.key_env} belum diatur; provider {spec.name} tidak dipanggil')
    prompt = json.dumps(data, ensure_ascii=False)
    headers = {}
    if spec.kind == 'gemini':
        url = f'{spec.url}/{selected}:generateContent'
        headers = {'x-goog-api-key': secret}
        body = {
            'systemInstruction': {'parts': [{'text': system}]},
            'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
            'generationConfig': {'responseMimeType': 'application/json', 'temperature': temperature},
        }
    elif spec.kind == 'anthropic':
        url = spec.url
        headers = {'x-api-key': secret, 'anthropic-version': '2023-06-01'}
        body = {
            'model': selected, 'max_tokens': 4096, 'temperature': temperature,
            'system': system + '\nRespond ONLY with a valid JSON object.',
            'messages': [{'role': 'user', 'content': prompt}],
        }
    elif spec.kind == 'ollama':
        # Intentionally restricted to loopback; an arbitrary env URL could lead to SSRF.
        url = spec.url
        body = {'model': selected, 'system': system + '\nReturn JSON object only.',
                'prompt': prompt, 'stream': False, 'format': 'json',
                'options': {'temperature': temperature}}
    else:
        url = spec.url
        headers = {'Authorization': 'Bearer ' + secret}
        body = {
            'model': selected, 'temperature': temperature,
            'messages': [{'role': 'system', 'content': system + '\nReturn valid JSON object only.'},
                         {'role': 'user', 'content': prompt}],
            'response_format': {'type': 'json_object'},
        }
    with httpx.Client(timeout=65.0, transport=transport, follow_redirects=False) as client:
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()
        raw = response.json()
    try:
        if spec.kind == 'gemini':
            text = ''.join(p['text'] for p in raw['candidates'][0]['content']['parts'] if 'text' in p)
        elif spec.kind == 'anthropic':
            text = ''.join(p['text'] for p in raw['content'] if p.get('type') == 'text')
        elif spec.kind == 'ollama':
            text = raw['response']
        else:
            text = raw['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise InvalidProviderResponse(f'Respons {spec.name} tidak mengandung konten JSON') from exc
    return _decode_json(text)


def generate_json(system: str, data: dict, *, temperature: float = 0.2,
                  provider: str | None = None, model: str | None = None,
                  transport=None, role: str = 'default') -> dict:
    """Select provider (optionally by role) and use controlled failover.

    Failover is OFF by default. Only a 429, 502, 503, or 504 HTTP error is
    eligible. Timeouts, malformed output and unknown outcomes never fail over.
    Paid provider failover requires AI_ALLOW_PAID_FALLBACK=true as well.
    """
    if role not in {'default', 'draft', 'rewrite'}:
        raise ValueError('Role tidak dikenal')
    primary = (provider or os.getenv('AI_' + role.upper() + '_PROVIDER')
               or os.getenv('AI_PROVIDER', 'gemini')).strip().lower()
    if primary not in PROVIDERS:
        raise ValueError(f'AI provider tidak didukung: {primary}. Pilihan: {", ".join(PROVIDERS)}')
    queue = [primary]
    if not provider and os.getenv('AI_ENABLE_FALLBACK', 'false').lower() == 'true':
        allowed_paid = os.getenv('AI_ALLOW_PAID_FALLBACK', 'false').lower() == 'true'
        for fallback in os.getenv('AI_FALLBACK_PROVIDERS', '').lower().split(','):
            fallback = fallback.strip()
            if fallback in PROVIDERS and fallback not in queue:
                if not PROVIDERS[fallback].possibly_billable or allowed_paid:
                    queue.append(fallback)
    for index, name in enumerate(queue):
        try:
            # An explicit model applies only to the primary provider; using its
            # identifier with a different provider would be invalid.
            return _single(PROVIDERS[name], system, data, temperature=temperature,
                           model=model if index == 0 else None, role=role, transport=transport)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (429, 502, 503, 504) and index < len(queue) - 1:
                continue
            raise
    raise RuntimeError('Tidak ada provider AI yang berhasil')
