"""A fake OpenAI / Anthropic / Gemini for gateway tests (httpx.MockTransport)."""
from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

import httpx


def sse(events: List[Dict], done: bool = False, named: bool = False) -> bytes:
    out = b""
    for e in events:
        if named:
            out += f"event: {e['type']}\n".encode()
        out += b"data: " + json.dumps(e).encode() + b"\n\n"
    if done:
        out += b"data: [DONE]\n\n"
    return out


class MockProviders:
    """Records every upstream request; `reply` decides each response."""

    def __init__(self):
        self.requests: List[httpx.Request] = []
        self.reply: Optional[Callable[[httpx.Request, Dict], httpx.Response]] = None
        self.texts: List[str] = []   # queue of answer texts (default answers otherwise)
        self.status: List[int] = []  # queue of status codes

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def next_text(self, default: str) -> str:
        return self.texts.pop(0) if self.texts else default

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = json.loads(request.content or b"{}") if request.method == "POST" else {}
        if self.reply is not None:
            return self.reply(request, body)
        status = self.status.pop(0) if self.status else 200
        if status >= 400:
            return httpx.Response(status, json={"error": {"message": "upstream exploded", "type": "server_error"}})
        host, path = request.url.host, request.url.path
        if "slack" in host or "hooks" in host or "webhook" in host:
            return httpx.Response(200, text="ok")
        if path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        if host == "api.openai.com":
            return self.openai(body)
        if host == "api.anthropic.com":
            return self.anthropic(body)
        if host == "generativelanguage.googleapis.com":
            return self.gemini(path, body)
        return httpx.Response(404, json={"error": "unknown host"})

    def openai(self, body):
        text = self.next_text("Paris is the capital of France.")
        if body.get("stream"):
            words = text.split(" ")
            chunks = [{"id": "c1", "object": "chat.completion.chunk", "model": body["model"],
                       "choices": [{"index": 0, "delta": {"content": w + (" " if i < len(words) - 1 else "")},
                                    "finish_reason": None}]} for i, w in enumerate(words)]
            chunks.append({"id": "c1", "object": "chat.completion.chunk", "model": body["model"],
                           "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            return httpx.Response(200, content=sse(chunks, done=True), headers={"content-type": "text/event-stream"})
        return httpx.Response(200, headers={"x-request-id": "req_123"}, json={
            "id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30}})

    def anthropic(self, body):
        text = self.next_text("Bonjour! How can I help?")
        if body.get("stream"):
            events = [
                {"type": "message_start", "message": {"id": "m1", "model": body["model"], "usage": {"input_tokens": 15, "output_tokens": 1}}},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                *[{"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}}
                  for t in [text[: len(text) // 2], text[len(text) // 2:]]],
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 7}},
                {"type": "message_stop"},
            ]
            return httpx.Response(200, content=sse(events, named=True), headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 15, "output_tokens": 7}})

    def gemini(self, path, body):
        text = self.next_text("The sky looks blue because of Rayleigh scattering.")
        resp = {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 10}}
        if "streamGenerateContent" in path:
            half = len(text) // 2
            chunks = [{"candidates": [{"content": {"role": "model", "parts": [{"text": text[:half]}]}}]},
                      {"candidates": [{"content": {"role": "model", "parts": [{"text": text[half:]}]}, "finishReason": "STOP"}],
                       "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 10}}]
            return httpx.Response(200, content=sse(chunks), headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=resp)
