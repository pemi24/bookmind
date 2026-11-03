"""Provider layer: JSON extraction/validation/retry, Ollama + Gemini transports (mocked HTTP),
provider selection and configuration messages. No network, Ollama or API keys needed."""
from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm.errors import LLMError
from app.llm.prompts.analysis import ChapterAnalysis, EntityOut
from app.llm.prompts.study import QuestionOut, QuizOut
from app.llm.providers import create_provider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.structured import extract_json, generate_validated, inline_schema, salvage


def settings(**kw) -> Settings:
    base = dict(llm_provider="ollama", llm_model="", llm_fast_model="", llm_json_retries=2,
                gemini_api_key="", anthropic_api_key="", ollama_host="http://ollama.test")
    base.update(kw)
    return Settings(_env_file=None, **base)


# ------------------------------------------------------------------ JSON extraction / validation

@pytest.mark.parametrize("text", [
    '{"a": 1}',
    'Sure! Here is the JSON:\n```json\n{"a": 1}\n```\nHope that helps.',
    'Result: {"a": 1,} trailing words',
    '```\n{"a": 1}\n```',
    'prefix {"a": 1} {"b": 2}',
])
def test_extract_json_tolerates_noise(text):
    assert extract_json(text) == {"a": 1}


def test_extract_json_strings_with_braces():
    assert extract_json('{"q": "use } and { inside", "n": [1, 2]}') == {"q": "use } and { inside", "n": [1, 2]}


def test_extract_json_failure():
    with pytest.raises(ValueError):
        extract_json("I cannot do that.")


def test_coercion_of_sloppy_small_model_output():
    e = EntityOut.model_validate({"name": "Alice", "kind": "Person", "aliases": None,
                                  "description": None, "importance": "high"})
    assert (e.kind, e.aliases, e.description, e.importance) == ("character", [], "", 4)
    q = QuestionOut.model_validate({"type": "MCQ", "question": "Q?", "options": "A, B, C", "answer": "A",
                                    "explanation": "x", "passage": "2"})
    assert q.type == "multiple_choice" and q.options == ["A", "B", "C"] and q.passage == 2


def test_salvage_drops_only_bad_items():
    data = {"entities": [{"name": "Alice", "kind": "character", "aliases": [], "description": "d", "importance": 3},
                         {"kind": "place"}],  # missing name -> dropped
            "relations": "not a list",  # coerced to a 1-item list, then dropped as invalid
            "events": []}
    out = salvage(ChapterAnalysis, data)
    assert [e.name for e in out.entities] == ["Alice"] and out.relations == []


def test_inline_schema_has_no_refs_and_keeps_title_fields():
    schema = inline_schema(QuizOut)
    s = json.dumps(schema)
    assert "$ref" not in s and "$defs" not in s
    assert schema["properties"]["title"]["type"] == "string"  # the quiz's own "title" field survives
    assert "title" not in schema["properties"]["questions"]["items"]  # schema annotations are removed


class Small(BaseModel):
    answer: int


async def test_generate_validated_retries_with_feedback():
    replies = iter(["no json here", '{"answer": "not a number"}', '{"answer": 42}'])
    prompts: list[str] = []

    async def raw(system, user):
        prompts.append(user)
        return next(replies)

    out = await generate_validated(raw, "sys", "question", Small, retries=2)
    assert out.answer == 42
    assert len(prompts) == 3 and "not valid" in prompts[1] and "answer" in prompts[2]


async def test_generate_validated_gives_up_with_clear_error():
    async def raw(system, user):
        return "still not json"

    with pytest.raises(LLMError) as e:
        await generate_validated(raw, "sys", "q", Small, retries=1)
    assert "malformed" in e.value.message


# ------------------------------------------------------------------ Ollama (mocked HTTP)

def ollama(handler, **kw) -> OllamaProvider:
    return OllamaProvider(settings(**kw), transport=httpx.MockTransport(handler))


async def test_ollama_stream_chat():
    seen = {}

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        seen.update(body)
        lines = [{"message": {"content": "Alice "}, "done": False},
                 {"message": {"content": "falls [1]."}, "done": False},
                 {"message": {"content": ""}, "done": True, "done_reason": "stop"}]
        return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines))

    p = ollama(handler)
    out = [c async for c in p.stream_chat("SYS", [{"role": "user", "content": "Q"}])]
    assert "".join(out) == "Alice falls [1]."
    assert seen["model"] == "qwen2.5:3b" and seen["stream"] is True
    assert seen["messages"][0] == {"role": "system", "content": "SYS"}
    assert seen["options"]["num_ctx"] == 8192


async def test_ollama_generate_json_uses_schema_and_retries():
    calls = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        calls.append(body)
        content = "oops" if len(calls) == 1 else '{"answer": 7}'
        return httpx.Response(200, json={"message": {"content": content}, "done": True})

    p = ollama(handler)
    out = await p.generate_json("sys", "q", Small)
    assert out.answer == 7 and len(calls) == 2
    assert calls[0]["format"]["properties"]["answer"]["type"] == "integer"  # constrained decoding
    assert calls[0]["options"]["temperature"] == 0.0
    assert "ONLY one JSON object" in calls[0]["messages"][0]["content"]


async def test_ollama_not_running_message():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    p = ollama(handler)
    with pytest.raises(LLMError) as e:
        _ = [c async for c in p.stream_chat("s", [{"role": "user", "content": "q"}])]
    assert "Ollama isn't running" in e.value.message and e.value.status == 503
    status = await p.check()
    assert not status.ok and "ollama.com/download" in status.message


async def test_ollama_model_not_pulled():
    def handler(request: httpx.Request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})
        return httpx.Response(404, json={"error": "model \"qwen2.5:3b\" not found, try pulling it first"})

    p = ollama(handler)
    with pytest.raises(LLMError) as e:
        await p.generate_json("s", "q", Small)
    assert "ollama pull qwen2.5:3b" in e.value.message
    status = await p.check()
    assert not status.ok and "ollama pull qwen2.5:3b" in status.message


async def test_ollama_check_ok_including_latest_tag():
    def handler(request):
        return httpx.Response(200, json={"models": [{"name": "llama3.1:latest"}]})

    assert (await ollama(handler, llm_model="llama3.1").check()).ok


def test_ollama_limits_follow_context_window():
    p = ollama(lambda r: httpx.Response(200), ollama_num_ctx=4096)
    assert p.local and p.default_top_k == 5 and p.max_input_chars < 10_000


# ------------------------------------------------------------------ Gemini (mocked HTTP)

def gemini(handler, **kw) -> GeminiProvider:
    return GeminiProvider(settings(llm_provider="gemini", gemini_api_key="test-key", **kw),
                          transport=httpx.MockTransport(handler))


async def test_gemini_stream_chat_maps_roles_and_parses_sse():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        events = [{"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}]}}]},
                  {"candidates": [{"content": {"parts": [{"text": "Hello "}]}}]},
                  {"candidates": [{"content": {"parts": [{"text": "[1]"}]}, "finishReason": "STOP"}]}]
        return httpx.Response(200, text="".join(f"data: {json.dumps(e)}\r\n\r\n" for e in events))

    p = gemini(handler)
    msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]
    out = "".join([c async for c in p.stream_chat("SYS", msgs)])
    assert out == "Hello [1]"  # thought parts are not shown
    assert ":streamGenerateContent" in seen["url"] and "alt=sse" in seen["url"] and seen["key"] == "test-key"
    assert [c["role"] for c in seen["body"]["contents"]] == ["user", "model", "user"]
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "SYS"


async def test_gemini_json_mode():
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"answer": 3}'}]}}]})

    assert (await gemini(handler).generate_json("s", "q", Small)).answer == 3


async def test_gemini_bad_key_and_missing_key():
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "API key not valid. Please pass a valid API key."}})

    with pytest.raises(LLMError) as e:
        await gemini(handler).generate_json("s", "q", Small)
    assert "GEMINI_API_KEY" in e.value.message
    unconfigured = GeminiProvider(settings(llm_provider="gemini"))
    assert not unconfigured.configured() and "GEMINI_API_KEY" in unconfigured.not_configured_message()
    assert not (await unconfigured.check()).ok


async def test_gemini_retired_model_reports_googles_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "This model is no longer available to new users."}})

    p = GeminiProvider(settings(llm_provider="gemini", gemini_api_key="k"), transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError) as e:
        async for _ in p.stream_chat("sys", [{"role": "user", "content": "hi"}]):
            pass
    assert "no longer available" in e.value.message and "LLM_MODEL" in e.value.message


async def test_gemini_retries_busy_answers(monkeypatch):
    from app.llm.providers import gemini as gmod

    monkeypatch.setattr(gmod, "_RETRY_DELAYS", (0.0, 0.0))
    calls = {"n": 0}
    busy = {"error": {"message": "This model is currently experiencing high demand."}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json=busy)
        if ":streamGenerateContent" in str(request.url):
            return httpx.Response(200, text='data: {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}\r\n\r\n')
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"answer": 1}'}]}}]})

    assert "".join([c async for c in gemini(handler).stream_chat("s", [{"role": "user", "content": "q"}])]) == "ok"
    assert calls["n"] == 2
    calls["n"] = 0
    assert (await gemini(handler).generate_json("s", "q", Small)).answer == 1 and calls["n"] == 2

    # The main model stays overloaded: after its retries, the fallback model answers.
    urls = []

    def main_busy(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        if "gemini-flash-lite-latest" not in str(request.url):
            return httpx.Response(503, json=busy)
        return httpx.Response(200, text='data: {"candidates": [{"content": {"parts": [{"text": "lite"}]}}]}\r\n\r\n')

    assert "".join([c async for c in gemini(main_busy).stream_chat("s", [{"role": "user", "content": "q"}])]) == "lite"
    assert len(urls) == 4 and "gemini-flash-lite-latest" in urls[-1]  # 3 tries on the main model, then the fallback

    def always_busy(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json=busy)

    calls["n"] = 0
    with pytest.raises(LLMError) as e:
        async for _ in gemini(always_busy).stream_chat("s", [{"role": "user", "content": "q"}]):
            pass
    assert calls["n"] == 6 and "temporarily unavailable" in e.value.message  # both models tried, then a clear error

    def bad_request(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "Invalid argument."}})

    calls["n"] = 0
    with pytest.raises(LLMError):
        await gemini(bad_request).generate_json("s", "q", Small)
    assert calls["n"] == 1  # not retried, and no fallback: another model wouldn't fix a bad request


# ------------------------------------------------------------------ registry / Anthropic

def test_create_provider_by_name_and_defaults():
    assert create_provider("ollama", settings()).model == "qwen2.5:3b"
    assert create_provider("Gemini", settings()).model == "gemini-3.5-flash"
    a = create_provider("anthropic", settings(llm_model="claude-sonnet-5-5"))
    assert a.model == "claude-sonnet-5-5" and not a.configured() and "ANTHROPIC_API_KEY" in a.not_configured_message()
    assert create_provider("ollama", settings(llm_model="llama3.1:8b", llm_fast_model="qwen2.5:3b")).fast_model == "qwen2.5:3b"
    with pytest.raises(LLMError):
        create_provider("openai", settings())


async def test_anthropic_unconfigured_raises_clear_error():
    a = create_provider("anthropic", settings())
    with pytest.raises(LLMError) as e:
        _ = [c async for c in a.stream_chat("s", [{"role": "user", "content": "q"}])]
    assert "ANTHROPIC_API_KEY" in e.value.message and e.value.status == 503
