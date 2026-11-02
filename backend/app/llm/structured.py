"""Structured (JSON) output for any model: extraction, validation, salvage and retry.

Small local models often wrap JSON in prose or code fences, add trailing commas, use a
synonym for an enum value, or get one list item wrong. This module:

1. pulls the first JSON object out of the reply (`extract_json`),
2. validates it against the Pydantic schema; if only some list items are invalid they
   are dropped instead of failing the whole response (`salvage`),
3. otherwise re-asks the model with the validation error (`generate_validated`), up to
   LLM_JSON_RETRIES extra attempts.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, get_args, get_origin

from pydantic import BaseModel, ValidationError

from app.llm.errors import LLMError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in `text` (tolerates fences, prose, trailing commas)."""
    if not isinstance(text, str):
        return text
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for cand in candidates:
        cand = cand.strip()
        start = min((i for i in (cand.find("{"), cand.find("[")) if i != -1), default=-1)
        if start == -1:
            continue
        # Walk to the matching closing bracket, respecting strings.
        stack, in_str, esc = [], False, False
        for i in range(start, len(cand)):
            ch = cand[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if not stack:
                    break
                stack.pop()
                if not stack:
                    body = cand[start:i + 1]
                    try:
                        return json.loads(body)
                    except json.JSONDecodeError:
                        return json.loads(_TRAILING_COMMA.sub(r"\1", body))
    raise ValueError("no JSON object found in the reply")


def _list_item_model(annotation) -> type[BaseModel] | None:
    if get_origin(annotation) is list:
        (item,) = get_args(annotation) or (None,)
        if isinstance(item, type) and issubclass(item, BaseModel):
            return item
    return None


def salvage(schema: type[T], data: Any) -> T:
    """Validate; if that fails, drop invalid items from list-of-model fields and try again."""
    try:
        return schema.model_validate(data)
    except ValidationError:
        if not isinstance(data, dict):
            raise
    fixed = dict(data)
    dropped = 0
    for name, field in schema.model_fields.items():
        item_model = _list_item_model(field.annotation)
        if item_model is None or name not in fixed:
            continue
        value = fixed[name]
        if not isinstance(value, list):  # a single object (or junk) where a list was expected
            value = [] if value is None else [value]
        good = []
        for item in value:
            try:
                good.append(item_model.model_validate(item).model_dump())
            except ValidationError:
                dropped += 1
        fixed[name] = good
    result = schema.model_validate(fixed)  # still raises if something non-list is wrong
    if dropped:
        log.info("Dropped %d invalid item(s) from %s output", dropped, schema.__name__)
    return result


def _short_error(e: Exception) -> str:
    if isinstance(e, ValidationError):
        parts = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:5]]
        return "; ".join(parts)
    return str(e)[:300]


# ---------------------------------------------------------------- schema helpers

def inline_schema(schema: type[BaseModel]) -> dict:
    """JSON Schema with $refs inlined and titles removed (friendlier for grammar engines)."""
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node, is_properties: bool = False):
        if isinstance(node, dict):
            if "$ref" in node and not is_properties:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            if is_properties:  # keys are field names (a field may be called "title")
                return {k: walk(v) for k, v in node.items()}
            return {k: walk(v, k == "properties") for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(raw)


def skeleton(node: dict) -> Any:
    """A compact example of the expected JSON shape, for the prompt."""
    if "anyOf" in node:
        non_null = [n for n in node["anyOf"] if n.get("type") != "null"]
        return skeleton(non_null[0]) if non_null else None
    if "enum" in node:
        return "|".join(str(v) for v in node["enum"])
    t = node.get("type")
    if t == "object":
        return {k: skeleton(v) for k, v in node.get("properties", {}).items()}
    if t == "array":
        return [skeleton(node.get("items", {}))]
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    return "..."


def json_instructions(schema: type[BaseModel]) -> str:
    shape = json.dumps(skeleton(inline_schema(schema)), ensure_ascii=False)
    return ("Reply with ONLY one JSON object, no other text, in exactly this shape "
            f"(\"a|b\" means choose one of the values):\n{shape}")


# ---------------------------------------------------------------- the retry loop

RawFn = Callable[[str, str], Awaitable[Any]]  # (system, user) -> raw text or parsed dict


async def generate_validated(raw_fn: RawFn, system: str, user: str, schema: type[T], retries: int) -> T:
    """Call the model, validate, and re-ask with the error message on failure."""
    prompt = user
    last_error = "unknown"
    for attempt in range(retries + 1):
        raw = await raw_fn(system, prompt)
        try:
            return salvage(schema, extract_json(raw))
        except (ValueError, ValidationError) as e:
            last_error = _short_error(e)
            log.warning("Invalid JSON from model (attempt %d/%d): %s", attempt + 1, retries + 1, last_error)
            snippet = raw if isinstance(raw, str) else json.dumps(raw)
            prompt = (f"{user}\n\nYour previous reply was not valid ({last_error}). "
                      f"Previous reply (start): {snippet[:300]!r}\n"
                      "Try again. Reply with ONLY the JSON object.")
    raise LLMError(f"The AI model kept returning malformed data ({last_error}). "
                   "Try again, or use a larger model (LLM_MODEL in backend/.env).", 502)
