import json
import httpx
import pytest
from backend.app.config import Settings
from backend.app.rag import OpenRouterGateway, OpenRouterError
from backend.app.schemas import GeneratedTriage


def gateway(handler, **settings):
    instance = OpenRouterGateway(Settings(openrouter_api_key='test-server-key', _env_file=None, **settings))
    instance.client.close()
    instance.client = httpx.Client(base_url='https://openrouter.ai/api/v1/', transport=httpx.MockTransport(handler))
    return instance


def test_openrouter_embedding_payload_order_and_separate_key():
    def handler(request):
        assert request.url.path == '/api/v1/embeddings'
        assert request.headers['Authorization'] == 'Bearer test-embedding-key'
        assert json.loads(request.content) == {'model': 'nvidia/nemotron-3-embed-1b:free', 'input': ['first', 'second'],
            'encoding_format': 'float', 'provider': {'max_price': {'prompt': 0, 'completion': 0, 'request': 0}}}
        return httpx.Response(200, json={'data': [{'index': 1, 'embedding': [0., 1.]}, {'index': 0, 'embedding': [1., 0.]}]})
    instance = gateway(handler, openrouter_embedding_api_key='test-embedding-key')
    try:
        assert instance.embed(['first', 'second']) == [[1., 0.], [0., 1.]]
        assert instance.embed([]) == []
    finally:
        instance.close()


def test_openrouter_generation_uses_strict_schema_and_main_key():
    schema = GeneratedTriage.model_json_schema()
    def handler(request):
        assert request.url.path == '/api/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer test-server-key'
        payload = json.loads(request.content)
        assert payload['model'] == 'nvidia/nemotron-3-super-120b-a12b:free'
        assert payload['reasoning'] == {'enabled': False}
        assert payload['provider'] == {'require_parameters': True, 'max_price': {'prompt': 0, 'completion': 0, 'request': 0}}
        assert payload['response_format']['json_schema'] == {'name': 'ticket_triage', 'strict': True, 'schema': schema}
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{"abstain":true}'}}]})
    instance = gateway(handler)
    try:
        assert instance.generate([{'role': 'user', 'content': 'Request'}], schema) == '{"abstain":true}'
    finally:
        instance.close()


@pytest.mark.parametrize('key', ['', 'your_openrouter_api_key_here', 'replace_with_key'])
def test_placeholder_keys_fail_before_a_network_request(key):
    instance = OpenRouterGateway(Settings(openrouter_api_key=key, _env_file=None))
    try:
        assert not instance.status()['available']
        with pytest.raises(OpenRouterError, match='OPENROUTER_API_KEY'):
            instance.embed(['request'])
    finally:
        instance.close()


@pytest.mark.parametrize('status', [401, 402, 403, 404, 429, 500])
def test_provider_errors_do_not_expose_raw_responses_or_keys(status):
    instance = gateway(lambda _: httpx.Response(status, json={'error': {'message': 'test-server-key private text'}}))
    try:
        with pytest.raises(OpenRouterError) as caught:
            instance.embed(['private request'])
        assert 'test-server-key' not in str(caught.value)
        assert 'private' not in str(caught.value)
    finally:
        instance.close()


@pytest.mark.parametrize('rows', [[], [{'index': 2, 'embedding': [1.]}],
    [{'index': 0, 'embedding': []}], [{'index': 0, 'embedding': [0., 0.]}],
    [{'index': 0, 'embedding': ['bad']}], [{'index': 0, 'embedding': [True]}]])
def test_invalid_embedding_responses_are_rejected(rows):
    instance = gateway(lambda _: httpx.Response(200, json={'data': rows}))
    try:
        with pytest.raises(OpenRouterError, match='invalid embeddings'):
            instance.embed(['request'])
    finally:
        instance.close()


@pytest.mark.parametrize('choice', [
    {'finish_reason': 'length', 'message': {'content': '{'}},
    {'finish_reason': 'stop', 'message': {'content': None, 'refusal': 'refused'}},
])
def test_truncated_and_refused_generations_are_visible_errors(choice):
    instance = gateway(lambda _: httpx.Response(200, json={'choices': [choice]}))
    try:
        with pytest.raises(OpenRouterError, match='truncated'):
            instance.generate([], {})
    finally:
        instance.close()


@pytest.mark.parametrize('field, model', [
    ('generation_model', 'openai/gpt-4.1-mini'),
    ('embedding_model', 'openai/text-embedding-3-small'),
    ('generation_model', 'openrouter/auto'),
])
def test_paid_models_and_automatic_paid_routing_are_rejected(field, model):
    with pytest.raises(ValueError, match='Paid models are blocked'):
        Settings(**{field: model}, _env_file=None)


def test_paid_model_cannot_bypass_runtime_guard():
    def forbidden(request):
        pytest.fail('A paid model request must never reach the network.')
    instance = gateway(forbidden)
    try:
        instance.settings = instance.settings.model_copy(update={'generation_model': 'openai/gpt-4.1-mini'})
        with pytest.raises(OpenRouterError, match='Paid models are blocked'):
            instance.generate([], {})
    finally:
        instance.close()


@pytest.mark.parametrize('status', [402, 429])
def test_free_quota_errors_do_not_recommend_payment(status):
    instance = gateway(lambda _: httpx.Response(status, json={'error': {'message': 'Provider quota'}}))
    try:
        with pytest.raises(OpenRouterError) as caught:
            instance.embed(['request'])
        assert 'add credits' not in str(caught.value).lower()
        assert 'free' in str(caught.value).lower()
    finally:
        instance.close()
