# glc_v3 patch: add Moonshot (Kimi) as a provider

Not part of the S14 assignment, but needed to run Atlas on `kimi-k3`. Moonshot's API is
OpenAI-compatible, so it is a subclass plus two registry lines.

Two real quirks are handled, both examples of provider capability drift:

1. **`kimi-k3` rejects any temperature except 1** with a 400. A caller asking for
   deterministic output is not wrong; the model simply does not offer that knob, so the
   provider pins it rather than letting a valid request fail at the edge.
2. **K3 always reasons.** It spends roughly 2700 output tokens thinking before emitting a
   token, and `reasoning: "off"` does not change that. A 1400 token cap therefore returns
   `stop_reason=max_tokens` with an empty string, which reads as a broken model but is a
   budget bug. Callers must budget for the think.

## `glc/providers.py`

```python
class MoonshotProvider(OpenAICompatProvider):
    """Moonshot AI (Kimi). OpenAI-compatible, so only the base URL differs.

    This is the international endpoint. The mainland China service is
    api.moonshot.cn/v1 and issues separate keys, so it is a config change
    rather than a second class.
    """

    name = "moonshot"
    capabilities = {**OpenAICompatProvider.capabilities, "reasoning": True}

    # kimi-k3 rejects any temperature other than 1 with a 400. Callers that ask
    # for deterministic output are not wrong, the model simply does not offer
    # that knob, so the provider pins it rather than letting a valid request
    # fail at the edge. This is the ordinary shape of provider capability drift.
    _FIXED_TEMPERATURE_MODELS = ("kimi-k3",)

    def __init__(self, api_key, model):
        super().__init__(
            api_key, model, os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1")
        )

    async def chat(self, messages, *, temperature=0.7, model=None, **kwargs):
        target = model or self.model
        if any(target.startswith(m) for m in self._FIXED_TEMPERATURE_MODELS):
            temperature = 1
        return await super().chat(messages, temperature=temperature, model=model, **kwargs)
```

Registry:

```python
    if k := os.getenv("MOONSHOT_API_KEY"):
        out["moonshot"] = MoonshotProvider(k, os.getenv("MOONSHOT_MODEL", "kimi-k3"))
```

## `glc/routing.py`

```python
    "moonshot": {"rpm": 30, "rpd": 9999, "tpm": 128000, "cooldown": 2, "max_ctx": 256000},
```
