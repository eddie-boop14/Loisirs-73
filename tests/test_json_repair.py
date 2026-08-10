#!/usr/bin/env python3
"""test_json_repair.py — the cs-failure class stays fixed.

The 2026-07-03 cs batch lost 140/389 results to unescaped double quotes
inside JSON string values (Czech quoted phrases emitted as literal '"').
parse_result_text now repairs that class before giving up; these seeds
prove the repair works, does not corrupt valid payloads, and still fails
honestly on garbage (validators + absent-field discipline untouched).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from translate_batch import parse_result_text, repair_json_quotes  # noqa: E402

fails = []


def ok(name, cond):
    if not cond:
        fails.append(name)
        print(f"  ✗ {name}")


# 1. the real cs failure shapes — interior straight quotes in values
out = parse_result_text('{"meta_title": "Vodopád „Královna Alp" u Sixt", "x": "ok"}')
ok("mixed typographic+straight quotes parse",
   out["x"] == "ok" and "Královna" in out["meta_title"])

out = parse_result_text('{"a": "Přezdívaný "Královna Alp" vodopád", "b": "čistý"}')
ok("interior straight quotes escaped, content preserved",
   out["a"] == 'Přezdívaný "Královna Alp" vodopád' and out["b"] == "čistý")

out = parse_result_text('{"a": "t", "b": {"c": "on řekl "ahoj" a odešel"}}')
ok("nested object with interior quotes", out["b"]["c"] == 'on řekl "ahoj" a odešel')

# 2. valid payloads are untouched (repair is only reached on parse failure,
#    and even applied directly it must be an identity on well-formed JSON)
valid = '{"a": "normal", "b": ["x", "y"], "c": {"d": "e"}, "n": 3}'
ok("valid JSON survives direct repair verbatim", repair_json_quotes(valid) == valid)
ok("valid JSON parses", parse_result_text(valid)["n"] == 3)

# 3. already-escaped quotes stay escaped (no double-escaping)
out = parse_result_text('{"a": "he said \\"hi\\""}')
ok("pre-escaped quotes unharmed", out["a"] == 'he said "hi"')

# 4. fenced output still stripped first
out = parse_result_text('```json\n{"a": "s "q" t"}\n```')
ok("fences + repair compose", out["a"] == 's "q" t')

# 5. genuinely broken payloads still fail (truncation — honesty preserved)
try:
    parse_result_text('{"a": "unterminated')
    ok("truncated payload must still raise", False)
except Exception:
    pass

if fails:
    print(f"test_json_repair: {len(fails)} FAILURE(S): {fails}")
    sys.exit(1)
print("test_json_repair: OK — cs quote-failure class repairs; valid/escaped/truncated behavior unchanged")
