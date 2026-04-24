# LinkedIn post — S03 submission

Posted 2026-04-24 alongside the Mini Perplexity demo video.

---

An agent is a `for` loop, a JSON parser, and 3 tools.

That's it. That's the whole thing.

Spent this weekend building Mini Perplexity from scratch — no LangChain, no frameworks. The "intelligence" isn't in the Python; it's in the system prompt's contract with the LLM. The loop just shuttles messages back and forth until the model emits `{"answer": ...}`.

Once you've built one of these by hand, every agentic framework becomes transparent — you can see exactly which sharp edge each abstraction is hiding.

→ Three tools: web_search (DuckDuckGo), fetch_page (trafilatura), save_answer (cited markdown)
→ Reasoning chain rendered live in the terminal + persisted to JSON for replay
→ Gemini 2.5 Pro as the brain, stop_sequences to keep it honest

Demo (3 min): https://youtu.be/w-UFTm1Vivw
Code + step-by-step walkthrough: https://github.com/levelscorner/mini-perplexity

S3 of EAG V3 from The School of AI shipped. Next: wrap the tools as an MCP server, add a memory layer, build an eval harness.

#AgenticAI #Python #LLM #BuildingInPublic #TheSchoolofAI
