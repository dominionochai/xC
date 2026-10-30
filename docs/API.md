# xC API

The API is rooted at `/`. JSON endpoints accept and return JSON unless noted. Request bodies are limited to 64 KB; larger requests receive `413 Payload Too Large`.

## Authentication and service limits

When `XC_API_TOKEN` is configured, send it as `Authorization: Bearer <token>`. Requests with a missing or invalid token receive `401 Unauthorized`; token comparison is constant-time. Authentication is optional when `XC_API_TOKEN` is not configured.

At most 3 runs may be active concurrently. A request that would exceed this limit receives `429` with the message `too many concurrent runs`. Each run has a default Qloo call budget of 60 calls and a default wall-clock limit of 90 seconds.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/resolve` | Resolve the supplied input and return the resolution result. |
| `POST` | `/api/v1/reports` | Create a report from the supplied request. |
| `GET` | `/api/v1/reports/{id}` | Retrieve a report by its identifier. |
| `POST` | `/api/v1/reports/{id}/generate` | Start report generation and return run information. |
| `POST` | `/api/v1/reports/{id}/generate/stream` | Start report generation and receive progress/results as a Server-Sent Events (SSE) stream. |
| `POST` | `/api/v1/reports/{id}/cancel` | Request cancellation of a report run. |
| `GET` | `/api/v1/reports/{id}/memo.md` | Retrieve the report memo as Markdown. |
| `GET` | `/api/v1/reports/{id}/memo.pdf` | PDF rendering is not implemented; this endpoint returns `501` with the note `pdf rendering not implemented`. |
| `GET` | `/health` | Check service health. |

## Run lifecycle

A report run moves through `pending` → `running` → `completed`, `failed`, or `cancelled`. Cancellation is a request; a run that has already reached a terminal state does not become active again.

When a report completes, the stream emits `report.completed` followed by `run.finished`.

## Streaming and replay

The stream uses SSE. Each frame uses this wire format, including the blank line that terminates the frame:

```text
event: <type>\ndata: <json>\n\n
```

Clients can reconnect with `Last-Event-ID` to request replay after the last event they received. Replay is available from a 5000-event buffer. If the requested run/event history can no longer be resumed, the server reports `RUN_NOT_RESUMABLE`; clients should treat that run's stream as non-resumable rather than assuming events were replayed.

## Legacy route

The legacy `POST /analyze` alias is deprecated and will be removed once the contract path is verified.
