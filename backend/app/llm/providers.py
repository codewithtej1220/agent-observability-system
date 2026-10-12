"""Provider adapters: read and write each provider's native wire format.

The gateway forwards requests byte-for-byte; adapters only *observe* them
(extract the prompt, response text, usage, streaming deltas) and, for
enforcement, build follow-up requests (repair turn, fallback model).

Supported endpoints
  openai     POST /v1/chat/completions, POST /v1/responses
  anthropic  POST /v1/messages
  gemini     POST /v1beta/models/{model}:generateContent | :streamGenerateContent
Anything else is proxied without analysis.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_settings


@dataclass
class Prompt:
    model: str
    system: str
    messages: List[Dict[str, str]]  # normalized [{"role", "content"}] text only
    stream: bool

    @property
    def last_user(self) -> str:
        for m in reversed(self.messages):
            if m["role"] == "user":
                return m["content"]
        return ""

    @property
    def all_text(self) -> str:
        return self.system + "\n" + "\n".join(m["content"] for m in self.messages)


@dataclass
class Completion:
    text: str = ""
    finish_reason: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    tool_calls: List[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n".join([self.text] + [f"[tool call] {t}" for t in self.tool_calls]).strip()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def _text_of(content: Any) -> str:
    """Flatten any provider's content (string or list of parts/blocks) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        content = [content]
    out = []
    for part in content:
        if isinstance(part, str):
            out.append(part)
        elif isinstance(part, dict):
            if "text" in part and isinstance(part["text"], str):
                out.append(part["text"])
            elif part.get("type") in ("image_url", "image", "input_image") or "inlineData" in part or "inline_data" in part:
                out.append("[image]")
            elif part.get("type") == "tool_result" or "functionResponse" in part:
                out.append("[tool result] " + _text_of(part.get("content") or part.get("functionResponse", {}).get("response")))
            elif part.get("type") == "tool_use" or "functionCall" in part:
                fc = part.get("functionCall") or part
                out.append(f"[tool call] {fc.get('name')}({json.dumps(fc.get('input') or fc.get('args') or {})[:300]})")
    return "\n".join(o for o in out if o)


def iter_sse(buffer: bytes) -> Tuple[List[str], bytes]:
    """Split complete SSE events off `buffer`; returns (data payloads, remaining bytes)."""
    events = []
    buffer = buffer.replace(b"\r\n", b"\n")
    while b"\n\n" in buffer:
        raw, buffer = buffer.split(b"\n\n", 1)
        data = [ln[5:].strip() for ln in raw.decode("utf-8", "replace").split("\n") if ln.startswith("data:")]
        if data:
            events.append("\n".join(data))
    return events, buffer


class StreamAccumulator:
    """Rebuilds the final completion from a stream while bytes pass through."""

    def __init__(self, adapter: "Adapter", path: str = ""):
        self.adapter = adapter
        self.path = path
        self.buffer = b""
        self.raw = bytearray()
        self.completion = Completion()
        self.saw_sse = False

    def feed(self, chunk: bytes) -> None:
        self.raw.extend(chunk)
        self.buffer += chunk
        events, self.buffer = iter_sse(self.buffer)
        for data in events:
            self.saw_sse = True
            if data == "[DONE]":
                continue
            try:
                self.adapter.apply_stream_event(json.loads(data), self.completion)
            except (json.JSONDecodeError, TypeError, KeyError, IndexError, AttributeError):
                continue

    def finish(self) -> Completion:
        if not self.saw_sse and self.raw:
            # e.g. Gemini streamGenerateContent without alt=sse returns a JSON array.
            try:
                body = json.loads(bytes(self.raw))
                for item in body if isinstance(body, list) else [body]:
                    self.adapter.apply_stream_event(item, self.completion)
                if not self.completion.text and not self.completion.tool_calls and isinstance(body, dict):
                    # Upstream ignored stream=true and sent a normal response.
                    self.completion = self.adapter.parse_response(self.path, body)
            except (json.JSONDecodeError, TypeError, KeyError, IndexError, AttributeError):
                pass
        return self.completion


class Adapter:
    name = ""
    generation_paths: Tuple[str, ...] = ()

    @property
    def base_url(self) -> str:
        raise NotImplementedError

    def is_generation(self, path: str, method: str) -> bool:
        return method == "POST" and any(re.search(p, path) for p in self.generation_paths)

    def upstream_url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def auth_headers(self, key: str) -> Dict[str, str]:
        raise NotImplementedError

    def passthrough_headers(self) -> Tuple[str, ...]:
        return ("content-type", "accept")

    def parse_request(self, path: str, body: Dict) -> Prompt:
        raise NotImplementedError

    def parse_response(self, path: str, body: Dict) -> Completion:
        raise NotImplementedError

    def apply_stream_event(self, ev: Dict, c: Completion) -> None:
        raise NotImplementedError

    def repair_request(self, path: str, body: Dict, previous: str, instruction: str) -> Dict:
        raise NotImplementedError

    def with_model(self, path: str, body: Dict, model: str) -> Tuple[str, Dict]:
        body = copy.deepcopy(body)
        body["model"] = model
        return path, body

    def simple_request(self, model: str, system: str, user: str, max_tokens: int = 800) -> Tuple[str, Dict]:
        raise NotImplementedError

    def models_path(self) -> str:
        raise NotImplementedError

    def error_body(self, message: str, code: str, details: Any = None) -> Dict:
        return {"error": {"type": code, "code": code, "message": message, "aobs": details}}


# --------------------------------------------------------------------------- OpenAI
class OpenAIAdapter(Adapter):
    name = "openai"
    generation_paths = (r"(^|/)v1/chat/completions$", r"(^|/)v1/responses$")

    @property
    def base_url(self) -> str:
        return get_settings().openai_base_url

    def auth_headers(self, key: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {key}"}

    def passthrough_headers(self):
        return ("content-type", "accept", "openai-organization", "openai-project", "openai-beta")

    @staticmethod
    def _is_responses(path: str) -> bool:
        return path.rstrip("/").endswith("responses")

    def parse_request(self, path, body):
        if self._is_responses(path):
            system = body.get("instructions") or ""
            inp = body.get("input", "")
            msgs = ([{"role": "user", "content": inp}] if isinstance(inp, str) else
                    [{"role": m.get("role", "user"), "content": _text_of(m.get("content"))} for m in inp if isinstance(m, dict)])
        else:
            system_parts, msgs = [], []
            for m in body.get("messages", []):
                role = m.get("role", "user")
                text = _text_of(m.get("content"))
                if role in ("system", "developer"):
                    system_parts.append(text)
                else:
                    msgs.append({"role": role, "content": text})
            system = "\n".join(system_parts)
        sys_msgs = [m for m in msgs if m["role"] in ("system", "developer")]
        if sys_msgs:  # responses API may carry system/developer items in input
            system = "\n".join([system] + [m["content"] for m in sys_msgs]).strip()
            msgs = [m for m in msgs if m["role"] not in ("system", "developer")]
        return Prompt(model=body.get("model", ""), system=system, messages=msgs, stream=bool(body.get("stream")))

    def parse_response(self, path, body):
        c = Completion()
        usage = body.get("usage") or {}
        if self._is_responses(path):
            for item in body.get("output", []):
                if item.get("type") == "message":
                    c.text += _text_of([p for p in item.get("content", []) if p.get("type") == "output_text"])
                elif item.get("type") == "function_call":
                    c.tool_calls.append(f"{item.get('name')}({item.get('arguments', '')[:300]})")
            c.finish_reason = body.get("status")
            c.input_tokens, c.output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
        else:
            choice = (body.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            c.text = _text_of(msg.get("content"))
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                c.tool_calls.append(f"{fn.get('name')}({fn.get('arguments', '')[:300]})")
            c.finish_reason = choice.get("finish_reason")
            c.input_tokens, c.output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
        return c

    def apply_stream_event(self, ev, c):
        t = ev.get("type", "")
        if t:  # Responses API events
            if t == "response.output_text.delta":
                c.text += ev.get("delta", "")
            elif t == "response.completed":
                resp = ev.get("response", {})
                u = resp.get("usage") or {}
                c.input_tokens, c.output_tokens = u.get("input_tokens"), u.get("output_tokens")
                c.finish_reason = resp.get("status")
            return
        for choice in ev.get("choices") or []:
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                c.text += delta["content"]
            for tc in delta.get("tool_calls") or []:
                fn = tc.get("function") or {}
                if fn.get("name"):
                    c.tool_calls.append(fn["name"] + "(…)")
            if choice.get("finish_reason"):
                c.finish_reason = choice["finish_reason"]
        if ev.get("usage"):
            c.input_tokens = ev["usage"].get("prompt_tokens")
            c.output_tokens = ev["usage"].get("completion_tokens")

    def repair_request(self, path, body, previous, instruction):
        body = copy.deepcopy(body)
        if self._is_responses(path):
            inp = body.get("input", "")
            items = [{"role": "user", "content": inp}] if isinstance(inp, str) else list(inp)
            body["input"] = items + [{"role": "assistant", "content": previous}, {"role": "user", "content": instruction}]
        else:
            body["messages"] = list(body.get("messages", [])) + [
                {"role": "assistant", "content": previous}, {"role": "user", "content": instruction}]
        return body

    def simple_request(self, model, system, user, max_tokens=800):
        body: Dict[str, Any] = {"model": model, "max_completion_tokens": max_tokens,
                                "messages": ([{"role": "system", "content": system}] if system else [])
                                + [{"role": "user", "content": user}]}
        if not re.match(r"^(o\d|gpt-5)", model):
            body["temperature"] = 0
        return "v1/chat/completions", body

    def models_path(self):
        return "v1/models"


# --------------------------------------------------------------------------- Anthropic
class AnthropicAdapter(Adapter):
    name = "anthropic"
    generation_paths = (r"(^|/)v1/messages$",)

    @property
    def base_url(self) -> str:
        return get_settings().anthropic_base_url

    def auth_headers(self, key):
        return {"x-api-key": key}

    def passthrough_headers(self):
        return ("content-type", "accept", "anthropic-version", "anthropic-beta")

    def parse_request(self, path, body):
        return Prompt(model=body.get("model", ""), system=_text_of(body.get("system")),
                      messages=[{"role": m.get("role", "user"), "content": _text_of(m.get("content"))}
                                for m in body.get("messages", [])],
                      stream=bool(body.get("stream")))

    def parse_response(self, path, body):
        c = Completion()
        for block in body.get("content", []):
            if block.get("type") == "text":
                c.text += block.get("text", "")
            elif block.get("type") == "tool_use":
                c.tool_calls.append(f"{block.get('name')}({json.dumps(block.get('input', {}))[:300]})")
        c.finish_reason = body.get("stop_reason")
        u = body.get("usage") or {}
        c.input_tokens, c.output_tokens = u.get("input_tokens"), u.get("output_tokens")
        return c

    def apply_stream_event(self, ev, c):
        t = ev.get("type")
        if t == "message_start":
            u = (ev.get("message") or {}).get("usage") or {}
            c.input_tokens = u.get("input_tokens")
            c.output_tokens = u.get("output_tokens")
        elif t == "content_block_start":
            block = ev.get("content_block") or {}
            if block.get("type") == "tool_use":
                c.tool_calls.append(f"{block.get('name')}(…)")
        elif t == "content_block_delta":
            d = ev.get("delta") or {}
            if d.get("type") == "text_delta":
                c.text += d.get("text", "")
        elif t == "message_delta":
            c.finish_reason = (ev.get("delta") or {}).get("stop_reason") or c.finish_reason
            if (ev.get("usage") or {}).get("output_tokens") is not None:
                c.output_tokens = ev["usage"]["output_tokens"]

    def repair_request(self, path, body, previous, instruction):
        body = copy.deepcopy(body)
        body["messages"] = list(body.get("messages", [])) + [
            {"role": "assistant", "content": previous}, {"role": "user", "content": instruction}]
        return body

    def simple_request(self, model, system, user, max_tokens=800):
        body = {"model": model, "max_tokens": max_tokens, "temperature": 0,
                "messages": [{"role": "user", "content": user}]}
        if system:
            body["system"] = system
        return "v1/messages", body

    def models_path(self):
        return "v1/models"


# --------------------------------------------------------------------------- Gemini
class GeminiAdapter(Adapter):
    name = "gemini"
    generation_paths = (r"models/[^/:]+:(generateContent|streamGenerateContent)$",)
    _model_re = re.compile(r"models/([^/:]+):")

    @property
    def base_url(self) -> str:
        return get_settings().gemini_base_url

    def auth_headers(self, key):
        return {"x-goog-api-key": key}

    def passthrough_headers(self):
        return ("content-type", "accept", "x-goog-api-client")

    def model_of(self, path: str) -> str:
        m = self._model_re.search(path)
        return m.group(1) if m else ""

    def parse_request(self, path, body):
        msgs = [{"role": "assistant" if c.get("role") == "model" else "user", "content": _text_of(c.get("parts"))}
                for c in body.get("contents", [])]
        si = body.get("systemInstruction") or body.get("system_instruction") or {}
        return Prompt(model=self.model_of(path), system=_text_of(si.get("parts") if isinstance(si, dict) else si),
                      messages=msgs, stream="streamGenerateContent" in path)

    def _apply(self, body: Dict, c: Completion, append: bool) -> None:
        cand = (body.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
        c.text = c.text + text if append else text
        for p in parts:
            if "functionCall" in p:
                fc = p["functionCall"]
                c.tool_calls.append(f"{fc.get('name')}({json.dumps(fc.get('args', {}))[:300]})")
        if cand.get("finishReason"):
            c.finish_reason = cand["finishReason"]
        u = body.get("usageMetadata") or {}
        if u:
            c.input_tokens = u.get("promptTokenCount", c.input_tokens)
            c.output_tokens = u.get("candidatesTokenCount", c.output_tokens)

    def parse_response(self, path, body):
        c = Completion()
        self._apply(body, c, append=False)
        return c

    def apply_stream_event(self, ev, c):
        self._apply(ev, c, append=True)

    def repair_request(self, path, body, previous, instruction):
        body = copy.deepcopy(body)
        body["contents"] = list(body.get("contents", [])) + [
            {"role": "model", "parts": [{"text": previous}]}, {"role": "user", "parts": [{"text": instruction}]}]
        return body

    def with_model(self, path, body, model):
        return self._model_re.sub(f"models/{model}:", path, count=1), copy.deepcopy(body)

    def simple_request(self, model, system, user, max_tokens=800):
        body: Dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": user}]}],
                                "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return f"v1beta/models/{model}:generateContent", body

    def models_path(self):
        return "v1beta/models"


ADAPTERS: Dict[str, Adapter] = {a.name: a for a in (OpenAIAdapter(), AnthropicAdapter(), GeminiAdapter())}


def get_adapter(provider: str) -> Adapter:
    try:
        return ADAPTERS[provider]
    except KeyError:
        raise ValueError(f"Unknown provider {provider}") from None
