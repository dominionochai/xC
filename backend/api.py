"""Optional HTTP API for xC. Core imports remain usable without FastAPI."""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import threading
import time
import uuid
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
except ImportError:  # FastAPI is an optional extra.
    FastAPI = None

MAX_BODY = 64 * 1024
MAX_RUNS = 3
RUN_TIMEOUT = 90.0
MAX_CALLS = int(os.getenv("XC_MAX_CALLS", "60"))
PACING_MS = int(os.getenv("XC_PACING_MS", "350"))


def create_app():
    """Return a configured FastAPI app, or None if the optional dependency is absent."""
    if FastAPI is None:
        return None

    from agents.events import EventBus
    from store.store import MemoryStore

    app = FastAPI(title="xC API", version="0.1.0")
    app.state.store = MemoryStore()
    app.state.buses = {}
    app.state.active = set()
    app.state.lock = threading.RLock()

    def authorized(request: Request) -> bool:
        expected = os.getenv("XC_API_TOKEN")
        if not expected:
            return True
        supplied = request.headers.get("authorization", "")
        prefix, _, token = supplied.partition(" ")
        return prefix.lower() == "bearer" and bool(token) and hmac.compare_digest(token, expected)

    @app.middleware("http")
    async def limits_and_auth(request: Request, call_next):
        if not authorized(request):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                if int(raw_length) > MAX_BODY:
                    return JSONResponse({"detail": "request body exceeds 64KB"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "invalid content-length"}, status_code=400)
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > MAX_BODY:
                return JSONResponse({"detail": "request body exceeds 64KB"}, status_code=413)
            sent = False
            async def receive():
                nonlocal sent
                if sent:
                    return {"type": "http.request", "body": b"", "more_body": False}
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            request._receive = receive
        return await call_next(request)

    def get_report(report_id: str):
        row = app.state.store.get_report(report_id)
        if row is None:
            raise HTTPException(status_code=404, detail="report not found")
        return row

    def reserve(report_id: str) -> bool:
        with app.state.lock:
            if report_id in app.state.active or len(app.state.active) >= MAX_RUNS:
                return False
            app.state.active.add(report_id)
            return True

    def release(report_id: str) -> None:
        with app.state.lock:
            app.state.active.discard(report_id)

    def run_report(report_id: str) -> dict:
        """Run the local resolver and assemble an honest, evidence-bounded report."""
        bus = app.state.buses[report_id]
        row = get_report(report_id)
        if bus.is_cancelled():
            app.state.store.update_report(report_id, {"status": "cancelled"})
            return {"id": report_id, "status": "cancelled", "warnings": ["cancelled"]}
        app.state.store.update_report(report_id, {"status": "running"})
        bus.emit("run.started", {"id": report_id})
        started = time.monotonic()
        payload = row.get("request", {})
        query = str(payload.get("query", ""))
        entity_type = payload.get("entity_type")
        result = {"matches": [], "selected": None, "confidence": 0.0,
                  "provenance": {"sources": ["qloo"]}, "evidence": [], "warnings": []}
        try:
            from backend.src.engine.resolve import resolve
            result = resolve(None, query, entity_type=entity_type,
                             budget=type("Budget", (), {"max_calls": MAX_CALLS, "call_count": 0})())
        except Exception as exc:
            result["warnings"].append("resolve_unavailable")
            result["error"] = str(exc)
        if time.monotonic() - started >= RUN_TIMEOUT:
            result.setdefault("warnings", []).append("wall_clock_deadline_exceeded")
        if bus.is_cancelled():
            status = "cancelled"
            result.setdefault("warnings", []).append("cancelled")
        else:
            status = "completed"
        full = {"id": report_id, "status": status, "result": result,
                "warnings": list(result.get("warnings", [])),
                "created_at": row.get("created_at"), "updated_at": time.time()}
        app.state.store.update_report(report_id, {"status": status, "result": result,
                                                  "report": full, "warnings": full["warnings"]})
        bus.emit("report.completed", full)
        bus.emit("run.finished", {"id": report_id, "status": status})
        return full

    async def bounded_run(report_id: str):
        try:
            return await asyncio.wait_for(asyncio.to_thread(run_report, report_id), timeout=RUN_TIMEOUT)
        except asyncio.TimeoutError:
            row = app.state.store.get_report(report_id) or {}
            warning = "wall_clock_deadline_exceeded"
            full = {"id": report_id, "status": "completed", "result": row.get("result", {}), "warnings": [warning]}
            app.state.store.update_report(report_id, {"status": "completed", "report": full, "warnings": [warning]})
            app.state.buses[report_id].emit("warning", {"message": warning})
            app.state.buses[report_id].emit("report.completed", full)
            app.state.buses[report_id].emit("run.finished", {"id": report_id, "status": "completed"})
            return full
        finally:
            release(report_id)

    def require_object(value: Any) -> dict:
        if not isinstance(value, dict):
            raise HTTPException(status_code=422, detail="JSON object required")
        return value

    @app.post("/api/v1/resolve")
    async def resolve_route(request: Request):
        """Resolve an entity through backend.src.engine.resolve with a stable response shape."""
        try:
            data = require_object(await request.json())
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=422, detail="invalid JSON")
        query = data.get("query")
        if not isinstance(query, str) or not query.strip():
            raise HTTPException(status_code=422, detail="query is required")
        from backend.src.engine.resolve import resolve
        budget = type("Budget", (), {"max_calls": MAX_CALLS, "call_count": 0})()
        return resolve(None, query, entity_type=data.get("entity_type"), budget=budget)

    @app.post("/analyze")
    async def legacy_analyze(request: Request):
        """Legacy alias removed once the contract path is verified."""
        return await resolve_route(request)

    @app.post("/api/v1/reports", status_code=201)
    async def create_report(request: Request):
        try:
            data = require_object(await request.json())
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=422, detail="invalid JSON")
        if not isinstance(data.get("query"), str) or not data["query"].strip():
            raise HTTPException(status_code=422, detail="query is required")
        report_id = str(uuid.uuid4())
        app.state.store.create_report({"id": report_id, "status": "pending", "request": data})
        app.state.buses[report_id] = EventBus()
        return {"id": report_id, "status": "pending"}

    @app.get("/api/v1/reports/{report_id}")
    async def read_report(report_id: str):
        return get_report(report_id)

    @app.post("/api/v1/reports/{report_id}/generate")
    async def generate_report(report_id: str):
        row = get_report(report_id)
        if row.get("status") in ("completed", "failed", "cancelled") and row.get("report"):
            return row["report"]
        if report_id not in app.state.buses:
            app.state.buses[report_id] = EventBus()
        if not reserve(report_id):
            raise HTTPException(status_code=429, detail="too many concurrent runs")
        return await bounded_run(report_id)

    @app.post("/api/v1/reports/{report_id}/generate/stream")
    async def generate_stream(report_id: str, request: Request):
        row = get_report(report_id)
        bus = app.state.buses.setdefault(report_id, EventBus())
        if row.get("status") == "completed" and row.get("report"):
            async def completed_replay():
                for typ, payload in (("report.completed", row["report"]),
                                     ("run.finished", {"id": report_id, "status": "completed"})):
                    yield f"event: {typ}\ndata: {json.dumps(payload, default=str)}\n\n"
            return StreamingResponse(completed_replay(), media_type="text/event-stream")
        last = request.headers.get("last-event-id")
        if last is None:
            last = request.query_params.get("last_event_id", "0")
        try:
            last_seq = max(0, int(last))
        except ValueError:
            raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer")
        if not reserve(report_id):
            if row.get("status") == "running":
                # A stream can attach to an existing run without reserving another worker.
                pass
            else:
                raise HTTPException(status_code=429, detail="too many concurrent runs")
        else:
            asyncio.create_task(bounded_run(report_id))
        async def events():
            cursor = last_seq
            idle = 0
            while True:
                retained = bus.get_run_events()
                if retained and cursor and cursor < retained[0]["seq"] - 1:
                    yield 'event: RUN_NOT_RESUMABLE\ndata: {"reason":"event history expired"}\n\n'
                    return
                batch = [ev for ev in retained if ev["seq"] > cursor]
                for ev in batch:
                    cursor = ev["seq"]
                    payload = ev.get("payload_preview", "null")
                    yield f"id: {ev['seq']}\nevent: {ev['type']}\ndata: {payload}\n\n"
                current = app.state.store.get_report(report_id) or {}
                if current.get("status") in ("completed", "failed", "cancelled") and not batch:
                    return
                if not batch:
                    idle += 1
                    if idle % 10 == 0:
                        yield ": keepalive\\n\\n"
                    await asyncio.sleep(0.1)
        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/v1/reports/{report_id}/cancel")
    async def cancel_report(report_id: str):
        row = get_report(report_id)
        bus = app.state.buses.setdefault(report_id, EventBus())
        bus.cancel()
        app.state.store.update_report(report_id, {"status": "cancelled"})
        bus.emit("run.cancelled", {"id": report_id})
        return {"ok": True}

    @app.get("/api/v1/reports/{report_id}/memo.md")
    async def memo_markdown(report_id: str):
        row = get_report(report_id)
        report = row.get("report", row)
        result = report.get("result", {}) if isinstance(report, dict) else {}
        return PlainTextResponse("# xC report\n\n" + json.dumps(result, indent=2, default=str) + "\n", media_type="text/markdown")

    @app.get("/api/v1/reports/{report_id}/memo.pdf")
    async def memo_pdf(report_id: str):
        get_report(report_id)
        return JSONResponse({"detail": "PDF rendering is not implemented"}, status_code=501)

    @app.get("/health")
    async def health():
        configured = bool(os.getenv("QLOO_API_KEY", "").strip()) and any(
            os.getenv(k, "").strip() for k in ("GEMINI_API_KEY", "XC_LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"))
        return {"status": "ok", "mode": "live" if configured else "fallback", "live": configured, "version": "0.1.0",
                "budget": {"max_calls": MAX_CALLS, "pacing_ms": PACING_MS}}

    return app


app = create_app()
