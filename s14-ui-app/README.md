# Atlas

An agent that may only answer in interfaces.

EAG V3 Session 14, Part 2. Every turn goes **model → declarative surface → injection wall →
render**. The model never writes markup, never names a component that does not exist, and never
emits an action the server did not register. What it returns is a JSON *description* of an
interface, checked before a pixel is drawn.

The gateway (`glc_v3`) owns the provider keys. This app holds none.

## Run it

```bash
# 1. glc_v3 on 8111 (Ollama backend, no provider keys needed)
cd glc_v3 && uv run glc serve

# 2. Atlas
cd s14-ui-app
uv sync
GLC_BASE_URL=http://127.0.0.1:8111 ATLAS_PROVIDER=ollama uv run python app.py
# open http://127.0.0.1:8120
```

## What it is

15 component types in a closed catalogue, 5 registered actions. The wall enforces the same three
invariants as S14Code:

| Invariant | Enforced by |
|---|---|
| **catalog** | a type not in the catalogue is refused, so `RawHtml` cannot exist |
| **data-not-code** | markup, `javascript:`/`data:`/`vbscript:` URLs and handler-shaped keys are refused at any depth in bound data |
| **event** | an action name outside the registered set never crosses back into the graph |

Rejection is surgical: a poisoned component is dropped and the rest of the surface still renders.

## Verified end to end

Live against `glc_v3` with `ollama/phi4:latest`, three turns carrying conversation forward:

| Turn | Asked | Composed | Refused |
|---|---|---|---|
| 1 | compare three languages, cite sources | Heading, **DataTable**, **EvidenceCard**, Button | 0 |
| 2 | show the migration risk | **Checklist**, **Timeline**, Button | 0 |
| 3 | trend over 6 months plus a headline number | **Sparkline**, **StatTile**, Checklist, Timeline, Button | 0 |

The component matches the shape of the data in every case: a comparison became a table, a
sourced claim became an EvidenceCard, a sequence became a Timeline, a trend became a Sparkline,
a single figure became a StatTile. No turn was a wall of text.

## The adversarial case

Press **Attack**, or `POST /turn_raw`, to push a hostile surface at the identical validator.
This is deliberately not something the model was talked into producing: it is handed straight to
the wall, so the wall is what is being tested.

```
ACCEPTED: ['c', 'ok']          <- the legitimate heading survives
REFUSED:
  m.text     [data-not-code] value carries markup
  u.sources  [data-not-code] source uri 'javascript:fetch(1)' is not an allowed scheme
  h.onclick  [data-not-code] event-handler property is never allowed
  x.onPress  [event        ] unregistered action 'transfer_funds'
  e.type     [catalog      ] unknown component type 'RawHtml'
```

All five attack classes refused, each naming the invariant it broke.

## The honest verdict

**The wall catches real drift, not just contrived attacks.** On an early turn 3, phi4 invented
`tone: "positive"` and `tone: "info"`. Both were refused by the enum and the components vanished
from the interface. That is the closed set doing exactly its job, and it is also the real cost of
this design: a weaker model drifts, and drift becomes missing UI rather than a wrong answer. The
fix was a better instruction, listing the four permitted tones explicitly, not a wider enum.
Widening the enum to accommodate the model would have dissolved the invariant it exists to hold.

**Declarative UI trades expressivity for a bounded attack surface, and the trade is real.**
Atlas cannot render anything outside 15 components. A generated-code approach could render
anything, at the cost of latency, variance and an execution path. For an agent surface I would
take this trade every time; for a marketing page I would not.

**What this does not solve.** The wall proves a value is inert, not that the caller was allowed
to see it: scope remains the memory service's job. There is no streaming, so a slow model means a
blank pause rather than progressive composition. And the client repeats the scheme check before
setting an `href`, which is defence in depth but is also a second policy in a second place that
can drift from the server's.

## Files

- `app.py` catalogue, validator, gateway seam, `/turn` and `/turn_raw`
- `client.html` renderers, built with `createElement` and text nodes. `innerHTML` appears nowhere.
