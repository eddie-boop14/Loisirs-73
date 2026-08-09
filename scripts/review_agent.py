#!/usr/bin/env python3
"""
review_agent.py — Job 3 / Phase 2 Job 8 prep
==============================================

AI Review Agent that triages signals from the weekly sweep before any human
touches Json/.

Pipeline:
  reports/review-queue.json  ──►  Claude Haiku 4.5  ──►  reports/review-verdicts.json
                                                            (artifact only — never auto-applied)

The agent NEVER touches Json/. Verdicts are advisory: a human reviews
review-verdicts.json and decides what (if anything) to change in the catalogue.

Usage:
  python3 scripts/review_agent.py                    # live run, calls Haiku
  python3 scripts/review_agent.py --dry-run          # skip API, placeholder verdicts
  python3 scripts/review_agent.py --queue PATH       # override queue path
  python3 scripts/review_agent.py --output PATH      # override output path

Env:
  ANTHROPIC_API_KEY  required for live runs (ignored in --dry-run)

Pricing (Haiku 4.5, 2026-06):
  input  $1.00 / MTok
  output $5.00 / MTok
"""

from __future__ import annotations
import siteconfig  # HANDOFF-73 phase 5: per-site identity

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# Paths & constants
# -----------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE = REPO_ROOT / "reports" / "review-queue.json"
DEFAULT_OUTPUT = REPO_ROOT / "reports" / "review-verdicts.json"
JSON_DIR = REPO_ROOT / "Json"

MODEL_ID = "claude-haiku-4-5-20251001"

# Pricing per million tokens (USD)
PRICE_IN_PER_MTOK = 1.00
PRICE_OUT_PER_MTOK = 5.00

# Slugs used to fabricate a mock queue when reports/review-queue.json is absent.
# All are real fiches in /home/user/Loisir-74/Json/.
MOCK_SLUGS = [
    "abbaye-d-aulps",
    "accrobranche-foret-aventures-manigod",
    "atelier-poterie-chez-el-annecy",
    "aire-de-decollage-parapente-plaine-joux",
]

# Per-slug fabricated conflicting signal so the mock queue is realistic.
MOCK_SIGNALS: dict[str, dict[str, str]] = {
    "abbaye-d-aulps": {
        "issue": "Google Places lists adult tariff at 8.50 EUR; fiche shows 7 EUR.",
        "source": "google_places",
        "detail": "Places (New) v1 placeDetails returned priceLevel.adult=8.50 EUR on 2026-06-09.",
        "checked": "2026-06-09",
    },
    "accrobranche-foret-aventures-manigod": {
        "issue": "Direct fetch of official_site_url returned HTTP 404.",
        "source": "direct_fetch",
        "detail": "GET https://www.manigod.com/a-vivre-en-famille/parcours-ludique-nature-en-foret.html -> 404 Not Found.",
        "checked": "2026-06-10",
    },
    "atelier-poterie-chez-el-annecy": {
        "issue": "Google Places reports 'permanently closed' status.",
        "source": "google_places",
        "detail": "Places (New) placeDetails business_status=CLOSED_PERMANENTLY on 2026-06-09; fiche still active.",
        "checked": "2026-06-09",
    },
    "aire-de-decollage-parapente-plaine-joux": {
        "issue": "Direct fetch returned redirect to a generic tourism office homepage.",
        "source": "direct_fetch",
        "detail": "GET https://www.passy-mont-blanc.com/ resolved 200 but page no longer mentions the takeoff site; possibly moved.",
        "checked": "2026-06-10",
    },
}

# -----------------------------------------------------------------------------
# Queue loading / fabrication
# -----------------------------------------------------------------------------


def _load_fiche(slug: str) -> dict[str, Any]:
    path = JSON_DIR / f"{slug}.json"
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def _fabricate_queue() -> list[dict[str, Any]]:
    """Build a mock 5-item queue from real fiches in Json/."""
    queue: list[dict[str, Any]] = []
    for slug in MOCK_SLUGS:
        path = JSON_DIR / f"{slug}.json"
        if not path.exists():
            print(f"[review] skipping missing fiche: {slug}", file=sys.stderr)
            continue
        fiche = _load_fiche(slug)
        name = (
            fiche.get("i18n", {})
            .get("fr", {})
            .get("name")
            or slug
        )
        signal = MOCK_SIGNALS[slug]
        queue.append(
            {
                "slug": slug,
                "issue": signal["issue"],
                "fiche_name": name,
                "existing_data": {
                    "category": fiche.get("category"),
                    "commune": fiche.get("commune"),
                    "official_site_url": fiche.get("official_site_url"),
                    "verify_flags": fiche.get("verify_flags", [])[:3],
                },
                "conflicting_signal": {
                    "source": signal["source"],
                    "detail": signal["detail"],
                    "checked": signal["checked"],
                },
            }
        )
    return queue


def load_queue(path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Returns (queue, was_fabricated)."""
    if path.exists():
        with path.open(encoding="utf-8") as fp:
            return json.load(fp), False
    return _fabricate_queue(), True


# -----------------------------------------------------------------------------
# Prompt construction
# -----------------------------------------------------------------------------

SYSTEM_PROMPT = (
    f"You are an editorial reviewer for {siteconfig.DOMAIN}, a {siteconfig.DEPT_NAME} tourism "
    "catalogue. You are auditing fiches against weekly sweep signals "
    "(Google Places, the French business registry, and direct fetches of "
    "official sites). Your verdicts get human-reviewed before any changes "
    "are applied to the catalogue — so be precise but do not be timid. "
    "Reply ONLY with a single compact JSON object: "
    '{"verdict": "confirm|reject|needs-human", "reasoning": "one short sentence"}. '
    "No prose outside the JSON."
)


def _user_prompt(item: dict[str, Any]) -> str:
    existing = item.get("existing_data", {}) or {}
    signal = item.get("conflicting_signal", {}) or {}
    lines = [
        f"Fiche: {item.get('fiche_name')} (slug: {item.get('slug')})",
        f"Issue: {item.get('issue')}",
        "",
        "Existing data:",
        f"  category: {existing.get('category')}",
        f"  commune: {existing.get('commune')}",
        f"  official_site_url: {existing.get('official_site_url')}",
        f"  verify_flags (sample): {existing.get('verify_flags')}",
        "",
        "Conflicting signal:",
        f"  source: {signal.get('source')}",
        f"  detail: {signal.get('detail')}",
        f"  checked: {signal.get('checked')}",
        "",
        "Verdict guidance:",
        '  "confirm"     — the signal is credible and the fiche likely needs the change',
        '  "reject"      — the signal is a false alarm; keep the fiche as-is',
        '  "needs-human" — ambiguous or high-stakes; route to a human reviewer',
    ]
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Anthropic call
# -----------------------------------------------------------------------------


def _parse_model_reply(text: str) -> tuple[str, str]:
    """Extract verdict + reasoning from the model's reply (compact JSON)."""
    text = text.strip()
    # Strip markdown fences if the model adds them despite instructions.
    if text.startswith("```"):
        text = text.strip("`")
        # remove an optional leading 'json' language tag
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()
    try:
        payload = json.loads(text)
        verdict = str(payload.get("verdict", "needs-human")).strip().lower()
        reasoning = str(payload.get("reasoning", "")).strip()
    except json.JSONDecodeError:
        return "needs-human", f"unparseable model reply: {text[:140]}"
    if verdict not in {"confirm", "reject", "needs-human"}:
        return "needs-human", f"unknown verdict '{verdict}': {reasoning}"
    return verdict, reasoning or "(no reasoning provided)"


def call_haiku(
    client: Any, item: dict[str, Any]
) -> tuple[str, str, int, int]:
    """Returns (verdict, reasoning, tokens_in, tokens_out)."""
    msg = client.messages.create(
        model=MODEL_ID,
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_prompt(item)}],
    )
    # SDK returns content as a list of blocks; we asked for plain text.
    parts = []
    for block in msg.content:
        text_attr = getattr(block, "text", None)
        if text_attr:
            parts.append(text_attr)
    reply = "".join(parts)
    verdict, reasoning = _parse_model_reply(reply)
    usage = getattr(msg, "usage", None)
    tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
    tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
    return verdict, reasoning, tokens_in, tokens_out


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def _now_z() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{siteconfig.WORDMARK} AI review agent")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip the API call; emit needs-human placeholders.",
    )
    parser.add_argument(
        "--queue",
        type=Path,
        default=DEFAULT_QUEUE,
        help=f"Queue JSON path (default: {DEFAULT_QUEUE}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output verdicts JSON path (default: {DEFAULT_OUTPUT}).",
    )
    args = parser.parse_args(argv)

    queue_path: Path = args.queue
    output_path: Path = args.output

    queue, fabricated = load_queue(queue_path)
    notes: list[str] = []
    if fabricated:
        notes.append(
            f"Queue file {queue_path} not found; fabricated a mock 5-item "
            "queue from real fiches in Json/."
        )

    verdicts: list[dict[str, Any]] = []
    total_in = 0
    total_out = 0

    if args.dry_run:
        notes.append("Dry-run: API call skipped; placeholders only.")
        for item in queue:
            verdicts.append(
                {
                    "slug": item.get("slug"),
                    "verdict": "needs-human",
                    "reasoning": "dry-run placeholder",
                    "tokens_in": 0,
                    "tokens_out": 0,
                }
            )
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print(
                "ERROR: ANTHROPIC_API_KEY not set. Use --dry-run for a placeholder run.",
                file=sys.stderr,
            )
            return 2
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError:
            print(
                "ERROR: anthropic SDK not installed. `pip install anthropic`.",
                file=sys.stderr,
            )
            return 2
        client = anthropic.Anthropic(api_key=api_key)
        for item in queue:
            try:
                verdict, reasoning, tin, tout = call_haiku(client, item)
            except Exception as exc:  # noqa: BLE001 — surface any SDK error
                verdict = "needs-human"
                reasoning = f"agent error: {type(exc).__name__}: {exc}"
                tin = tout = 0
                notes.append(f"{item.get('slug')}: {reasoning}")
            verdicts.append(
                {
                    "slug": item.get("slug"),
                    "verdict": verdict,
                    "reasoning": reasoning,
                    "tokens_in": tin,
                    "tokens_out": tout,
                }
            )
            total_in += tin
            total_out += tout

    cost = (total_in / 1_000_000.0) * PRICE_IN_PER_MTOK + (
        total_out / 1_000_000.0
    ) * PRICE_OUT_PER_MTOK

    payload = {
        "run_at": _now_z(),
        "model": MODEL_ID,
        "items_processed": len(verdicts),
        "verdicts": verdicts,
        "cost_estimate_usd": round(cost, 6),
        "notes": notes,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
        fp.write("\n")

    print(
        f"Wrote {output_path} — {len(verdicts)} verdict(s), "
        f"cost_estimate_usd={payload['cost_estimate_usd']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
