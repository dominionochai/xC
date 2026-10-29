# METHODS - W5 as-built (addendum)

Append/merge this into METHODS.md once a local checkout is available.

## W5 as-built

### W3 engine phases - Qloo call counts
- resolution: 2, fit: 2, contrast: 2, communities: ~N, simulation: 0, bridge: up to 12, locality: up to 3*len(regions), tam: 0
- total within Budget max_calls=40 at pacing_ms=350

### W4 agents / events / store / api
- agents: tools.py (7 ToolSpecs), llm.py (LiteLLM + template fallback), phases.py (5 phases, ledger-validated narration), events.py (seq bus, 5k buffer, cancel, keepalive)
- store: memory + sqlite
- api: resolve, reports, generate (+stream), cancel, memo.md, memo.pdf, health

### W5 memo export + robustness
- backend/src/services/memo_export.py: render_investment_memo_markdown / render_investment_memo_pdf, deterministic bytes, fixture header 'FIXTURE DATA - NOT LIVE QLOO OUTPUT'
- backend/robustness.py: sanitize_name, resolve_with_robustness (retries + partial), Cache (24h TTL), RunLimiter, SafeLogger (no secrets)
- W2 methods unchanged per W3 as-built