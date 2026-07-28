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

Live against `glc_v3`, three turns carrying the conversation forward, on `moonshot/kimi-k3`:

| Turn | Asked | Composed | Refused |
|---|---|---|---|
| 1 | compare three languages, cite sources | Heading, Text, **DataTable**, **BarChart**, **EvidenceCard**, **StatTile**, **Notice**, Choice | 0 |
| 2 | show the migration risk | **Checklist**, **Timeline**, DataTable, StatTile, Notice, Choice | 0 |
| 3 | trend over 6 months plus a headline number | **Sparkline**, **StatTile**, **KeyValue**, EvidenceCard, Notice | 1 |

The component matches the shape of the data in every case: a comparison became a table and a
chart, a sourced claim became an EvidenceCard, a sequence became a Timeline, a trend became a
Sparkline, a single figure became a StatTile. No turn was a wall of text.

Model choice changes composition quality sharply. Same prompts, same wall:

| | `ollama/phi4` | `moonshot/kimi-k3` |
|---|---|---|
| component types, turn 1 | 5 | **9** |
| latency per turn | 15 to 40s | ~100s |
| rejections | 0 | 0 |

K3 always reasons, spending roughly 2,700 output tokens before it emits a character, and
`reasoning: "off"` does not change that. A 1,400 token cap therefore returns
`stop_reason=max_tokens` with an empty string, which reads as a broken model and is really a
budget bug. `ATLAS_MAX_TOKENS` defaults to 6,000 for that reason.

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

**The wall also had a false positive, and finding it mattered more than the attacks.** The deep
scan refused any key matching `^on[a-z]+$` anywhere inside bound data. Kimi placed a legitimate
`onPick` inside an option object and lost its entire "next steps" control. The same rule would
have refused ordinary data fields called `online`, `once` or `only`, which is a bug waiting to
happen in any real dataset.

The fix was to be precise about where the danger actually is. At the **property** level anything
handler-shaped is still refused, because a property is a slot the renderer reads. Inside **data**
the check is now the real DOM handler names, because the renderer never turns a data key into an
attribute: values reach the DOM through `textContent`. Verified after the change: the five attack
classes are still refused, a nested `onerror` in table data is still caught, and a column named
`online` now renders. A wall that refuses safe things trains you to widen it, which is how walls
die.

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
