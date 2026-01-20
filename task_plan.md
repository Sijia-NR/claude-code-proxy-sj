## Goal
- Adapt Claude proxy to forward requests to the semantic LLM service described in `claude-code-proxy-main/大模型智能应用服务接口规范.txt` (语义大模型接口) while keeping Claude Code compatibility.

## Context / Constraints
- Current proxy maps Claude -> OpenAI-compatible API via `OpenAIClient`.
- Need new provider configuration (auth via `Authorization: APP_KEY`, custom endpoint) and request/response conversions compatible with existing Claude models.
- Streaming responses use SSE `data:` lines similar to OpenAI.

## Plan
1) Add configuration switches for provider selection and IAS endpoint/auth keys.
2) Implement IAS client (httpx) with non-stream and SSE stream support plus cancellation hook.
3) Add converter from Claude request to IAS payload (reuse existing mapping where possible).
4) Wire endpoints to select OpenAI vs IAS path; reuse existing Claude response converters.
5) Smoke-check locally (unit/manual) and update docs/config notes.

## Open Questions
- Default IAS base URL/path and whether to use `/V2` variant.
- Any required preservation of `appId/globalTraceId` back to caller (likely omit for Claude).
