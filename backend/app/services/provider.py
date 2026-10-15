import math
import httpx

class OpenRouterError(ValueError):
    """A safe provider error that never includes credentials or request data."""


class OpenRouterGateway:
    def __init__(self, settings):
        self.settings = settings
        self.client = httpx.Client(base_url=settings.openrouter_base_url.rstrip('/') + '/',
                                   timeout=settings.inference_timeout)

    def close(self):
        self.client.close()

    def _key(self, embedding=False):
        separate = self.settings.openrouter_embedding_api_key.get_secret_value().strip()
        key = separate if embedding and separate else self.settings.openrouter_api_key.get_secret_value().strip()
        if not key or key.lower().startswith(('your_', 'replace_', 'sk-or-your')):
            name = 'OPENROUTER_EMBEDDING_API_KEY or OPENROUTER_API_KEY' if embedding else 'OPENROUTER_API_KEY'
            raise OpenRouterError(f'Set {name} on the server to enable OpenRouter.')
        return key

    def status(self):
        try:
            self._key()
            self._key(embedding=True)
            return {'available': True, 'message': 'Free OpenRouter models configured. Paid routing is blocked; requests verify free-provider access.'}
        except OpenRouterError as error:
            return {'available': False, 'message': str(error)}

    def _request(self, path, payload, embedding=False):
        model = payload.get('model', '')
        if not isinstance(model, str) or not model.endswith(':free') or '/' not in model:
            raise OpenRouterError('Paid models are blocked. Choose an OpenRouter model ID ending in :free.')
        payload = {**payload, 'provider': {**payload.get('provider', {}),
            'max_price': {'prompt': 0, 'completion': 0, 'request': 0}}}
        response = self.client.post(path, json=payload, headers={
            'Authorization': 'Bearer ' + self._key(embedding), 'X-Title': 'Triage Desk'})
        if response.is_error:
            messages = {401: 'API key is invalid.', 402: 'Free request refused. Check the key budget and free-model access. No paid fallback was attempted.',
                        403: 'Access denied. Check API-key and provider permissions.',
                        404: 'Model unavailable. Check the configured model ID.',
                        429: 'Free-model quota or rate limit reached. Wait and retry; rules and manual decisions remain available.'}
            raise OpenRouterError('OpenRouter: ' + messages.get(response.status_code,
                f'Request failed (HTTP {response.status_code}). Check model availability and structured-output support.'))
        try:
            data = response.json()
        except ValueError as error:
            raise OpenRouterError('OpenRouter returned an invalid JSON response.') from error
        if not isinstance(data, dict) or data.get('error'):
            raise OpenRouterError('OpenRouter could not complete the request. Check provider status and retry.')
        return data

    def embed(self, texts: list[str]):
        if not texts:
            return []
        data = self._request('embeddings', {'model': self.settings.embedding_model,
                             'input': texts, 'encoding_format': 'float'}, embedding=True)
        try:
            rows = sorted(data['data'], key=lambda row: row['index'])
            if [row['index'] for row in rows] != list(range(len(texts))):
                raise ValueError('Embedding indices did not match the inputs.')
            vectors = [row['embedding'] for row in rows]
            dimension = len(vectors[0])
            if not dimension or any(len(v) != dimension or any(isinstance(n, bool) or not isinstance(n, (int, float))
                or not math.isfinite(n) for n in v) or not any(v) for v in vectors):
                raise ValueError('Invalid embedding vector.')
            return vectors
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise OpenRouterError('OpenRouter returned incomplete or invalid embeddings.') from error

    def generate(self, messages, schema):
        response = self._request('chat/completions', {
            'model': self.settings.generation_model, 'messages': messages, 'temperature': 0,
            'reasoning': {'enabled': False},
            'max_tokens': 1800, 'stream': False, 'provider': {'require_parameters': True},
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'ticket_triage', 'strict': True, 'schema': schema}}})
        try:
            choice = response['choices'][0]
            content = choice['message']['content']
            if choice.get('finish_reason') != 'stop' or not isinstance(content, str) or not content.strip():
                raise ValueError('Incomplete generation.')
            return content
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise OpenRouterError('OpenRouter returned an empty, refused, or truncated response. Retry or choose another model.') from error


