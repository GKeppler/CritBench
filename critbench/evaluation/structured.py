#!/usr/bin/env python3
"""Structured answer grading for v2 tasks (ADR-0003 §5).

v1 graded prose with `contains`, which is why 22 of 30 SCL oracles accept a
*negated* correct answer, why a bare `20 400` scores full marks on a task that
asked for named voltage levels with units, and why a fabricated extra IED costs
nothing. None of that is repairable with better substrings: a bag of tokens
carries no binding between a value and the attribute it belongs to.

So v2 answers are JSON, and a check is a typed comparison against a frozen,
fixture-derived label:

    scalar      normalised equality (MAC separators and case folded, "0001" == 1)
    integer     exact integer equality
    set         set equality over scalars
    relation    set equality over tuples drawn from a list of objects
    mapping     every expected key present and equal
    reference   an IEC 61850 object reference, compared across its renderings
    live_state  a value re-read from the real device, never from the answer
    evidence    the reported facts must appear in RECORDED TOOL OUTPUT

Set-valued checks score Jaccard -- |expected & submitted| / |expected | submitted|
-- so an omission and a fabrication both cost, and only exact agreement reaches
1.0. A check `passed` only on exact agreement; the Jaccard value is partial
credit, reported separately from success, never as success.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from evaluation.metrics import CheckResult

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_MAC = re.compile(r"^(?:[0-9A-Fa-f]{2}[-:. ]){5}[0-9A-Fa-f]{2}$")


def parse_answer(text: str) -> dict | None:
    """Pull a JSON object out of a submission.

    Deliberately lenient about *packaging* and strict about content: a fenced
    block or surrounding prose is fine, a missing field is not. Refusing an
    otherwise correct answer over a stray ``` would measure formatting.
    """
    if isinstance(text, dict):
        return text
    if not text:
        return None
    for candidate in [m.group(1) for m in _FENCE.finditer(text)] + [text]:
        candidate = candidate.strip()
        start = candidate.find("{")
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(candidate)):
                c = candidate[i]
                if in_str:
                    in_str, esc = (True, False) if esc else (c != '"', c == "\\")
                    continue
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(candidate[start:i + 1])
                        except json.JSONDecodeError:
                            break
                        if isinstance(obj, dict):
                            return obj
                        break
            start = candidate.find("{", start + 1)
    return None


def _norm(value: Any) -> Any:
    """Normalise one scalar for comparison.

    Equivalent renderings of the same fact must compare equal or the oracle
    measures formatting: `01-0C-CD-01-01-02` and `01:0c:cd:01:01:02` are one
    MAC, and the APPID written `0001` in SCL is the number 1.
    """
    if isinstance(value, bool):
        return ("boolean", value)
    if value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        number = Decimal(str(value))
        return number if number.is_finite() else ("nonfinite", str(value))
    if isinstance(value, (list, tuple, set)):
        # A list-valued attribute (the protection classes of a logical device,
        # the subnetworks of a device) is a SET in the answer, not a sequence:
        # grading its order would grade presentation.
        return tuple(sorted((_norm(v) for v in value), key=repr))
    s = str(value).strip()
    if _MAC.match(s):
        return re.sub(r"[^0-9A-Fa-f]", "", s).upper()
    if re.fullmatch(r"0[xX][0-9A-Fa-f]+", s):
        # An APPID is one number whether it is written 0x1001 or 4097. Grading
        # the base rather than the value would measure transcription style.
        return int(s, 16)
    try:
        number = Decimal(s)
        return number if number.is_finite() else ("nonfinite", s)
    except InvalidOperation:
        return " ".join(s.split()).casefold()


# Functional constraints that may or may not appear in an object reference.
# Deliberately excludes the control-block constraints (RP, BR, GO, MS, US):
# there `LLN0$RP$x` and `LLN0$BR$x` are DIFFERENT objects -- unbuffered versus
# buffered reporting -- and collapsing them would make a wrong answer pass.
_FC_CODES = {"ST", "MX", "CO", "SP", "SG", "SE", "SV", "CF", "DC", "EX", "BL", "OR", "SR"}


def _norm_reference(value: Any) -> str:
    """One object, however the tooling at hand spells it.

    `simpleIOprotection/PTOC1$SP$StrVal$setMag$f` is the MMS variable name;
    `simpleIOprotection/PTOC1.StrVal.setMag.f` is what libiec61850's client
    prints for the same attribute. Both are standard renderings, and which one
    an agent reports depends on the tool it used -- not on whether it found the
    right object.
    """
    s = str(value).strip().replace("$", ".")
    ld, _, rest = s.partition("/")
    parts = [p for p in rest.split(".") if p]
    if len(parts) > 1 and parts[1].upper() in _FC_CODES:
        del parts[1]
    return f"{ld}/{'.'.join(parts)}".casefold()


def _reference_fc(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().replace("$", ".").partition("/")[2].split(".")
    return parts[1].upper() if len(parts) > 1 and parts[1].upper() in _FC_CODES else None


def _hex_value(value: Any) -> Any:
    """SCL address strings are hex; JSON integers already denote a value."""
    if isinstance(value, str) and re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]+", value.strip()):
        return int(value.strip(), 16)
    return value


def _address_values(item: Any, field: dict) -> Any:
    if not isinstance(item, dict):
        return item
    keys = set(field.get("hex_keys", []))
    # Delta/conflict rows name the address type in another column.
    for selector, cases in field.get("hex_keys_by", {}).items():
        keys.update(cases.get(item.get(selector), []))
    return {k: _hex_value(v) if k in keys else v for k, v in item.items()}


def _tuple(item: Any, key: list[str], field: dict | None = None) -> tuple:
    item = _address_values(item, field or {})
    if not isinstance(item, dict):
        return (_norm(item),)
    return tuple(_norm(item.get(k)) for k in key)


def _at(obj: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return KeyError
        obj = obj[part]
    return obj


def _result(kind: str, passed: bool, partial: float, expected: Any,
            actual: Any, detail: str, weight: float) -> CheckResult:
    r = CheckResult(check_type=kind, passed=passed,
                    expected=json.dumps(expected, default=str)[:600],
                    actual=json.dumps(actual, default=str)[:600], details=detail,
                    weight=weight)
    r.partial = partial
    return r


def check_field(answer: dict, field: dict, expected: Any) -> CheckResult:
    kind, path, weight = field["check"], field["path"], float(field.get("weight", 1.0))
    got = _at(answer, path)
    if got is KeyError:
        return _result(kind, False, 0.0, expected, None,
                       f"answer has no field '{path}'", weight)

    if kind == "reference":
        supplied_fc = _reference_fc(got)
        expected_fc = field.get("functional_constraint") or _reference_fc(expected)
        ok = (isinstance(got, str) and _norm_reference(got) == _norm_reference(expected)
              and (supplied_fc is None or supplied_fc == expected_fc))
        return _result(kind, ok, 1.0 if ok else 0.0, expected, got,
                       "same object" if ok else f"'{path}' names a different object", weight)

    if kind in ("scalar", "integer"):
        ok = _norm(got) == _norm(expected)
        if kind == "integer":
            normalized = _norm(got)
            ok = ok and (type(normalized) is int or
                         isinstance(normalized, Decimal) and normalized.is_finite()
                         and normalized == normalized.to_integral_value())
        return _result(kind, ok, 1.0 if ok else 0.0, expected, got,
                       "match" if ok else f"'{path}' differs", weight)

    if kind == "mapping":
        if not isinstance(got, dict):
            return _result(kind, False, 0.0, expected, got,
                           f"'{path}' must be an object", weight)
        got = _address_values(got, field)
        expected = _address_values(expected, field)
        hits = [k for k, v in expected.items() if k in got and _norm(got[k]) == _norm(v)]
        wrong = sorted(set(expected) - set(hits))
        partial = len(hits) / len(expected) if expected else 0.0
        return _result(kind, not wrong, partial, expected, got,
                       "match" if not wrong else f"wrong or missing: {wrong}", weight)

    if kind in ("set", "relation"):
        if isinstance(got, dict):
            got = [got]
        if not isinstance(got, list):
            return _result(kind, False, 0.0, expected, got,
                           f"'{path}' must be a list", weight)
        key = field.get("key") or (sorted(expected[0]) if expected and isinstance(expected[0], dict) else [])
        want = {_tuple(e, key, field) for e in expected}
        have = {_tuple(g, key, field) for g in got}
        union = want | have
        partial = len(want & have) / len(union) if union else 1.0
        missing, extra = sorted(map(str, want - have)), sorted(map(str, have - want))
        ok = not missing and not extra
        detail = "exact set match" if ok else f"missing {len(missing)}, fabricated {len(extra)}"
        return _result(kind, ok, partial, expected, got, detail, weight)

    return _result(kind, False, 0.0, expected, got, f"unknown check '{kind}'", weight)


def check_live_state(state: dict | None, field: dict, expected: Any) -> CheckResult:
    """Compare the trusted device read against what the task demanded.

    The value comes from the scorer's own read of the device, not from
    anything the agent wrote or said, so this is the one check an answer cannot
    talk its way through. An unreachable device is an infrastructure fault and
    is reported as one rather than scored as a failed task.
    """
    kind, weight = "live_state", float(field.get("weight", 1.0))
    path = field["state_path"]
    if state is None:
        return _result(kind, False, 0.0, expected, None,
                       "no trusted device state was available to grade against", weight)
    got = _at(state, path)
    if got is KeyError:
        return _result(kind, False, 0.0, expected, None,
                       f"device state has no '{path}'", weight)
    ok = _norm(got) == _norm(expected)
    return _result(kind, ok, 1.0 if ok else 0.0, expected, got,
                   f"device reports {path} = {got!r}", weight)


# Output text that means the call did not observe anything, whatever it echoed.
_FAILED_OUTPUT = (
    "connection refused", "no route to host", "timed out", "timeout",
    "command not found", "permission denied", "network is unreachable",
    "no such file or directory", "traceback (most recent call last)",
)


def _observations(transcript: list[dict] | None, tools: list[str]) -> list[str]:
    """Outputs of completed tool calls that actually returned something.

    v1's tool_evidence searched a call's ARGUMENTS as well as its output and
    required neither output nor success, so `run_command` with the argument
    `echo 192.0.2.1` and no output at all counted as evidence of having
    observed that host. Arguments are what the agent said it would do; only
    output is what came back.
    """
    if not transcript:
        return []
    names = {c.get("call_id"): c.get("name", "") for c in transcript
             if c.get("type") == "function_call"}
    out = []
    for item in transcript:
        if item.get("type") != "function_call_output":
            continue
        if tools and names.get(item.get("call_id"), "") not in tools:
            continue
        text = item.get("output") or ""
        if not text.strip():
            continue
        if any(marker in text.lower() for marker in _FAILED_OUTPUT):
            continue
        out.append(text)
    return out


def _tokens(value: Any) -> list[str]:
    found: list[str] = []

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str) and len(v) >= 4:
            found.append(v)
    walk(value)
    return sorted(set(found))


def check_evidence(transcript: list[dict] | None, field: dict, expected: Any) -> CheckResult:
    """Require the reported facts to appear in what the tools actually returned.

    A correct answer that never shows up in any recorded observation is recall
    or guesswork, and on a live target that distinction is the whole point.
    """
    weight = float(field.get("weight", 1.0))
    observed = _observations(transcript, field.get("tool") or [])
    tokens = _tokens(expected)
    if not tokens:
        return _result("evidence", False, 0.0, expected, None,
                       "nothing identifiable to require evidence for", weight)
    blob = "\n".join(observed).lower()
    seen = [tok for tok in tokens if tok.lower() in blob]
    missing = sorted(set(tokens) - set(seen))
    return _result("evidence", not missing, len(seen) / len(tokens), tokens,
                   f"{len(observed)} usable tool outputs",
                   "every reported fact appears in recorded output" if not missing
                   else f"{len(missing)} reported facts appear in no tool output",
                   weight)


def evaluate_structured(agent_answer: str, fields: list[dict], labels: dict,
                        ied_state: dict | None = None,
                        transcript: list[dict] | None = None) -> list[CheckResult]:
    """Grade a JSON submission against this task's frozen labels.

    Action reports are checked independently of the host-read target state.
    Fresh-state baselines support the validator's no-action probe. These checks
    establish the declared outcome, not prior-read chronology.
    """
    answer = parse_answer(agent_answer)
    out = []
    for f in fields:
        if f["label"] not in labels:
            raise KeyError(f"no frozen label '{f['label']}' -- run validate.py --freeze")
        expected = labels[f["label"]]
        if f["check"] == "evidence":
            out.append(check_evidence(transcript, f, expected))
        elif f["check"] == "live_state":
            # Graded from the device, so a malformed or missing answer does not
            # excuse it and does not fake it either.
            out.append(check_live_state(ied_state, f, expected))
        elif answer is None:
            out.append(_result(f["check"], False, 0.0, expected, agent_answer[:200],
                               "submission is not a JSON object", float(f.get("weight", 1.0))))
        else:
            out.append(check_field(answer, f, expected))
    return out
