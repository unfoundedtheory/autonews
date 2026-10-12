"""Offline contract tests: never send actual API traffic during CI."""
import json
import httpx
import pytest
from utbot.ai_provider import PROVIDERS, generate_json, configured_providers, InvalidProviderResponse


def _answer(kind):
    if kind == 'gemini':
        return {'candidates': [{'content': {'parts': [{'text': '{"headline":"Benar"}'}]}}]}
    if kind == 'anthropic':
        return {'content': [{'type': 'text', 'text': '{"headline":"Benar"}'}]}
    if kind == 'ollama':
        return {'response': '{"headline":"Benar"}'}
    return {'choices': [{'message': {'content': '{"headline":"Benar"}'}}]}


@pytest.mark.parametrize('name', list(PROVIDERS))
def test_all_provider_payloads_offline(monkeypatch, name):
    spec = PROVIDERS[name]
    if spec.key_env:
        monkeypatch.setenv(spec.key_env, 'placeholder-only-test')
    calls=[]
    def handler(req):
        calls.append(req)
        body=json.loads(req.content)
        assert body['model'] if spec.kind != 'gemini' else body['contents']
        if spec.kind == 'openai':
            assert body['response_format'] == {'type': 'json_object'}
            assert req.headers['authorization'] == 'Bearer placeholder-only-test'
        if spec.kind == 'anthropic':
            assert req.headers['anthropic-version']=='2023-06-01'
        if spec.kind == 'ollama':
            assert req.url.host == '127.0.0.1'
            assert body['stream'] is False
        return httpx.Response(200, json=_answer(spec.kind))
    result = generate_json('System: JSON', {'sumber': 'NASA'}, provider=name,
                           transport=httpx.MockTransport(handler))
    assert result == {'headline':'Benar'}
    assert len(calls)==1


def test_role_selection_draft_vs_rewrite(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('AI_DRAFT_PROVIDER','deepseek')
    monkeypatch.setenv('AI_REWRITE_PROVIDER','groq')
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-deepseek')
    monkeypatch.setenv('GROQ_API_KEY','test-groq')
    monkeypatch.setenv('AI_REWRITE_MODEL','custom-role-model')
    seen=[]
    def handler(req):
        seen.append((req.url.host, json.loads(req.content)['model']))
        return httpx.Response(200,json=_answer('openai'))
    transport=httpx.MockTransport(handler)
    generate_json('JSON',{},role='draft',transport=transport)
    generate_json('JSON',{},role='rewrite',transport=transport)
    assert seen[0][0]=='api.deepseek.com'
    assert seen[1] == ('api.groq.com','custom-role-model')


def test_no_implicit_paid_provider_fallback(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','fake')
    monkeypatch.setenv('DEEPSEEK_API_KEY','fake')
    monkeypatch.setenv('AI_ENABLE_FALLBACK','true')
    monkeypatch.setenv('AI_ALLOW_PAID_FALLBACK','false')
    monkeypatch.setenv('AI_FALLBACK_PROVIDERS','deepseek')
    calls=[]
    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(429,json={'error':'quota'})
    with pytest.raises(httpx.HTTPStatusError):
        generate_json('JSON',{},transport=httpx.MockTransport(handler))
    assert calls == ['generativelanguage.googleapis.com']


def test_explicit_paid_fallback_on_quota_only(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','fake')
    monkeypatch.setenv('DEEPSEEK_API_KEY','fake')
    monkeypatch.setenv('AI_ENABLE_FALLBACK','true')
    monkeypatch.setenv('AI_ALLOW_PAID_FALLBACK','true')
    monkeypatch.setenv('AI_FALLBACK_PROVIDERS','deepseek')
    called=[]
    def handler(req):
        called.append(req.url.host)
        if len(called)==1:
            return httpx.Response(429,json={'error':'quota'})
        return httpx.Response(200,json=_answer('openai'))
    assert generate_json('JSON',{},transport=httpx.MockTransport(handler))['headline']=='Benar'
    assert called==['generativelanguage.googleapis.com','api.deepseek.com']


def test_invalid_json_never_triggers_fallback(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','fake')
    monkeypatch.setenv('DEEPSEEK_API_KEY','fake')
    monkeypatch.setenv('AI_ENABLE_FALLBACK','true')
    monkeypatch.setenv('AI_ALLOW_PAID_FALLBACK','true')
    monkeypatch.setenv('AI_FALLBACK_PROVIDERS','deepseek')
    hosts=[]
    def handler(req):
        hosts.append(req.url.host)
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'not json'}]}}]})
    with pytest.raises(InvalidProviderResponse):
        generate_json('JSON',{},transport=httpx.MockTransport(handler))
    assert hosts == ['generativelanguage.googleapis.com']


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    with pytest.raises(RuntimeError, match='OPENROUTER_API_KEY'):
        generate_json('JSON',{},provider='openrouter')


def test_configured_providers_never_returns_secrets(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','very-secret-xyz')
    names=configured_providers()
    assert 'deepseek' in names and 'very-secret-xyz' not in str(names)


def test_model_override_does_not_flow_into_fallback(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','x')
    monkeypatch.setenv('DEEPSEEK_API_KEY','x')
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('AI_ENABLE_FALLBACK','true')
    monkeypatch.setenv('AI_ALLOW_PAID_FALLBACK','true')
    monkeypatch.setenv('AI_FALLBACK_PROVIDERS','deepseek')
    models=[]
    def handler(req):
        if req.url.host == 'generativelanguage.googleapis.com':return httpx.Response(429)
        models.append(json.loads(req.content)['model'])
        return httpx.Response(200,json=_answer('openai'))
    generate_json('JSON',{},model='gemini-special',transport=httpx.MockTransport(handler))
    assert models==[PROVIDERS['deepseek'].default_model]
