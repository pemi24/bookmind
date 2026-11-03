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


async def test_gemini_daily_quota_goes_straight_to_fallback(monkeypatch):
    from app.llm.providers import gemini as gmod

    monkeypatch.setattr(gmod, "_RETRY_DELAYS", (0.0, 0.0))
    monkeypatch.setattr(gmod, "_exhausted", {})
    quota = {"error": {"code": 429, "message": "You exceeded your current quota", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "20"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "62326s"}]}}
    urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        if "gemini-flash-lite-latest" in str(request.url):
            return httpx.Response(200, text='data: {"candidates": [{"content": {"parts": [{"text": "lite"}]}}]}\r\n\r\n')
        return httpx.Response(429, json=quota)

    p = gemini(handler)
    out = "".join([c async for c in p.stream_chat("s", [{"role": "user", "content": "q"}])])
    assert out == "lite" and len(urls) == 2  # no retries on a used-up daily quota
    urls.clear()
    out = "".join([c async for c in p.stream_chat("s", [{"role": "user", "content": "q"}])])
    assert out == "lite" and len(urls) == 1 and "gemini-flash-lite-latest" in urls[0]  # remembered: main model skipped
    assert p.fast_model == "gemini-flash-lite-latest"  # side tasks spare the main model's quota


# ------------------------------------------------------------------ Groq / OpenRouter and the backup chain

def compat(name, handler, **kw):
    from app.llm.providers.openai_compat import PRESETS, OpenAICompatProvider

    s = settings(**{f"{name}_api_key": "k", **kw})
    return OpenAICompatProvider(s, PRESETS[name], transport=httpx.MockTransport(handler))


def sse(*texts: str, finish: str = "stop") -> httpx.Response:
    events = [{"choices": [{"delta": {"content": t}}]} for t in texts]
    events.append({"choices": [{"delta": {}, "finish_reason": finish}]})
    return httpx.Response(200, text="".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n")


async def test_openai_compatible_stream_and_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return sse("Terah ", "was Abram's father [1].")

    p = compat("groq", handler)
    out = "".join([c async for c in p.stream_chat("SYS", [{"role": "user", "content": "q"}])])
    assert out == "Terah was Abram's father [1]."
    assert seen["url"].endswith("/openai/v1/chat/completions") and seen["auth"] == "Bearer k"
    b = seen["body"]
    assert b["model"] == "openai/gpt-oss-120b" and b["messages"][0] == {"role": "system", "content": "SYS"}
    assert b["max_tokens"] <= 1500 and b["reasoning_effort"] == "low"  # fits Groq's free per-minute token limit


async def test_openai_compatible_errors_and_limits():
    daily = {"error": {"message": "Rate limit reached for model `openai/gpt-oss-120b` on tokens per day (TPD): "
                                  "Limit 200000, Used 199999. Please try again in 7m30s."}}
    p = compat("groq", lambda r: httpx.Response(429, json=daily))
    with pytest.raises(LLMError) as e:
        async for _ in p.stream_chat("s", [{"role": "user", "content": "q"}]):
            pass
    assert e.value.status == 429 and "daily" in e.value.message and e.value.retry_after == 600  # at least 10 min

    minute = {"error": {"message": "Rate limit reached on requests per minute (RPM). Please try again in 2s."}}
    with pytest.raises(LLMError) as e:
        await compat("groq", lambda r: httpx.Response(429, json=minute)).generate_json("s", "q", Small)
    assert e.value.retry_after == 2.0

    with pytest.raises(LLMError) as e:  # OpenRouter: only free models, never a paid one
        await compat("openrouter", lambda r: sse("x"), openrouter_model="openai/gpt-5").generate_json("s", "q", Small)
    assert e.value.status == 400 and ":free" in e.value.message
    assert not compat("groq", lambda r: sse("x"), groq_api_key="").configured()


async def test_groq_requests_are_shrunk_to_fit():
    from app.llm.prompts.chat import build_overview, build_system, build_user_turn
    from types import SimpleNamespace as N

    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return sse("ok")

    ps = [N(book_id=1, book_title="A", chapter_title=f"Ch {i}", page_start=i, page_end=i, text="word " * 400)
          for i in range(1, 13)]
    system = build_system(overview=build_overview("Alice", None, [(f"C{i}", "One. " + "Two. " * 80) for i in range(30)]))
    p = compat("groq", handler)
    assert "".join([c async for c in p.stream_chat(system, [{"role": "user", "content": build_user_turn("Why?", ps, memory=True)}])]) == "ok"
    sent = sum(len(m["content"]) for m in seen["body"]["messages"])
    assert sent <= 16_000 and seen["body"]["messages"][-1]["content"].rstrip().endswith("Answer:")


class FakeProvider:
    """Stands in for a provider in chain tests: scripted outcomes per call."""

    def __init__(self, name, outcomes, model="m", fast="f"):
        self.name, self.outcomes, self.calls, self.model, self.fast_model = name, list(outcomes), [], model, fast
        self.settings, self.local, self.max_input_chars, self.default_top_k = settings(), False, 1000, 8

    def configured(self):
        return True

    async def stream_chat(self, system, messages, *, model=None, max_tokens=4096, effort=None):
        self.calls.append(model)
        out = self.outcomes.pop(0)
        for chunk in out if isinstance(out, list) else []:
            if isinstance(chunk, LLMError):
                raise chunk
            yield chunk
        if isinstance(out, LLMError):
            raise out

    async def generate_json(self, system, user, schema, *, model=None, max_tokens=4096, effort=None):
        self.calls.append(model)
        out = self.outcomes.pop(0)
        if isinstance(out, LLMError):
            raise out
        return out


async def test_provider_chain_moves_on_and_remembers_used_up_quotas():
    from app.llm.providers.chain import ChainProvider

    async def ask(chain):
        return "".join([c async for c in chain.stream_chat("s", [{"role": "user", "content": "q"}], model="m")])

    used_up = LLMError("Gemini's free daily quota is used up.", 429, retry_after=60_000)
    main = FakeProvider("gemini", [used_up, used_up], model="gemini-3.5-flash", fast="gemini-lite")
    groq = FakeProvider("groq", [["fast ", "answer"], ["again"]], model="gpt-oss-120b", fast="gpt-oss-20b")
    chain = ChainProvider([main, groq])
    assert await ask(chain) == "fast answer"
    assert groq.calls == ["gpt-oss-120b"]  # the main model's name is translated to the backup's
    assert await ask(chain) == "again" and len(main.calls) == 1  # used-up main provider is skipped until reset

    # The main provider's quick-task model maps to the backup's quick-task model.
    main2 = FakeProvider("gemini", [LLMError("busy", 503)], model="gemini-3.5-flash", fast="gemini-lite")
    groq2 = FakeProvider("groq", [Small(answer=1)], model="gpt-oss-120b", fast="gpt-oss-20b")
    assert (await ChainProvider([main2, groq2]).generate_json("s", "q", Small, model="gemini-lite")).answer == 1
    assert groq2.calls == ["gpt-oss-20b"]


async def test_provider_chain_never_mixes_answers_or_hides_real_errors():
    from app.llm.providers.chain import ChainProvider

    # Failed halfway through: the error is shown rather than a second provider's answer glued on.
    half = FakeProvider("gemini", [["Alice ", LLMError("Google's content filter stopped this answer", 422)]])
    other = FakeProvider("groq", [["other"]])
    with pytest.raises(LLMError):
        "".join([c async for c in ChainProvider([half, other]).stream_chat("s", [{"role": "user", "content": "q"}])])
    assert other.calls == []

    # A bad API key isn't something another provider fixes silently: report it.
    bad_key = FakeProvider("gemini", [LLMError("The Gemini API key was rejected.", 401)])
    with pytest.raises(LLMError) as e:
        await ChainProvider([bad_key, FakeProvider("groq", [Small(answer=1)])]).generate_json("s", "q", Small)
    assert "rejected" in e.value.message

    # Everyone busy: the last provider's message is shown.
    a = FakeProvider("gemini", [LLMError("busy", 503)])
    b = FakeProvider("groq", [LLMError("Groq's free daily limit is used up.", 429, retry_after=600)])
    with pytest.raises(LLMError) as e:
        await ChainProvider([a, b]).generate_json("s", "q", Small)
    assert "Groq" in e.value.message


async def test_provider_chain_waits_out_a_brief_rate_limit(monkeypatch):
    from app.llm.providers import chain as chain_mod
    from app.llm.providers.chain import ChainProvider

    waits = []

    async def fake_sleep(s):
        waits.append(s)

    monkeypatch.setattr(chain_mod.asyncio, "sleep", fake_sleep)
    groq = FakeProvider("groq", [LLMError("Groq is rate-limiting requests.", 429, retry_after=3.0), ["fast"]])
    slow = FakeProvider("openrouter", [["slow"]])
    out = "".join([c async for c in ChainProvider([groq, slow]).stream_chat("s", [{"role": "user", "content": "q"}])])
    assert out == "fast" and waits == [3.5] and slow.calls == []  # waited a few seconds instead of switching

    long_wait = FakeProvider("groq", [LLMError("Groq's free daily limit is used up.", 429, retry_after=3600)])
    slow2 = FakeProvider("openrouter", [["slow"]])
    out = "".join([c async for c in ChainProvider([long_wait, slow2]).stream_chat("s", [{"role": "user", "content": "q"}])])
    assert out == "slow"
