# xC API

Versioned API base path: `/api/v1`. JSON endpoints accept and return JSON unless noted. Request bodies are limited to 64 KB; larger requests are rejected with `413 Payload Too Large`.

## Authentication and service limits

If `XC_API_TOKEN` is configured, send it as `Authorization: Bearer <token>`. Requests with a missing or invalid token receive `401 Unauthorized`. Authentication is optional when the service is configured without a token.

At most three runs may be active concurrently. Requests that would exceed this limit are rejected with `429 Too Many Requests`. Each run is subject to a Qloo budget of 60 seconds and a total wall-clock budget of 90 seconds.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/resolve` | Resolve the supplied input and return the resolution result. |
| `POST` | `/api/v1/reports` | Create a report from the supplied request. |
| `GET` | `/api/v1/reports/{report_id}` | Retrieve a report by its identifier. |
| `POST` | `/api/v1/generate` | Start generation and return its run information. |
| `POST` | `/api/v1/generate/stream` | Start generation and receive progress/results as a Server-Sent Events (SSE) stream. |
| `POST` | `/api/v1/runs/{run_id}/cancel` | Request cancellation of a run. |
| `GET` | `/api/v1/memo.md` | Retrieve the memo as Markdown. |
| `GET` | `/api/v1/memo.pdf` | PDF export is not implemented; this endpoint returns `501 Not Implemented`. No PDF payload is produced. |
| `GET` | `/health` | Check service health. |

### Run lifecycle

A run moves from `queued` to `running`, then reaches a terminal state: `completed`, `failed`, or `cancelled`. Cancellation is a request; a run that has already reached a terminal state does not become active again. Run generation is bounded by the limits above.

### Streaming and replay

The stream uses SSE. Each frame has exactly this wire format, including the blank line terminating the frame:

```text
event: <type>
data: <json>

```

Clients can reconnect with `Last-Event-ID` to request replay after the last event they received. If the requested run/event history cannot be resumed, the server reports `RUN_NOT_RESUMABLE`; clients should treat that run's stream as non-resumable rather than assuming events were replayed.

## Legacy route

Legacy `POST /analyze` is deprecated and will be removed once the contract path is verified.
