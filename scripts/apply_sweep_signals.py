#!/usr/bin/env python3
"""apply_sweep_signals.py — JOB 8. Connect sweep_loisirs74 + check_loisirs74
output to the JOB 6 state machine.

Rule:
  DEMOTE to draft if any of:
    - freshness.status == "CLOSED"
    - google_check.status == "CLOSED_PERMANENTLY"
    - google_check.status == "NOT_A_BUSINESS"
    - freshness.site_reachable is False AND google_check confirms not OPERATIONAL
  FLAG for review (no demotion) if:
    - google_check.status == "CLOSED_TEMPORARILY"  (could be seasonal)
    - freshness.status == "UNKNOWN" / "NEEDS_REVIEW"
  UPGRADE freshness date if:
    - google_check.status == "OPERATIONAL" and our cached check is older than current

Never silently deletes — every demotion writes a research_log entry and is
surfaced in reports/job8-sweep-demotions.md so you see it before deploy.

Idempotent: re-running with same signals produces no changes.

CLI:
    python3 scripts/apply_sweep_signals.py             # apply + report
    python3 scripts/apply_sweep_signals.py --dry-run   # report only, no write
    python3 scripts/apply_sweep_signals.py --simulate-dead-venue <slug>
        # write a synthetic CLOSED_PERMANENTLY into google_check on <slug>
        # for end-to-end gate test, then apply.
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / "Json"

TODAY = datetime.date.today().isoformat()


def check_is_valid(block):
    """ERROR ≠ DATA (HANDOFF-24): a CHECK_FAILED result — or a legacy block
    written by a failed call (status ERROR) — is a fact about the checker,
    not the venue. It carries NO signal: no demotion, no flag."""
    if not block:
        return False
    if block.get("check_failed") or block.get("outcome") == "CHECK_FAILED":
        return False
    if block.get("status") == "ERROR":
        return False
    return True


def signal_for(d):
    """Return ('demote' | 'flag' | None, reason_str).

    Rule — conservative: auto-demote ONLY on high-confidence convergence
    of multiple sources. Everything else flags for human review.

    DEMOTE when:
      - freshness.status == "CLOSED" AND freshness.confidence == "high"
    FLAG when:
      - any negative signal that isn't high-confidence:
        - freshness.status == "CLOSED" with confidence != "high"
        - google_check.status in (CLOSED_PERMANENTLY, NOT_A_BUSINESS,
          CLOSED_TEMPORARILY)
        - site unreachable CONFIRMED by two failed fetches on different
          days (a single bad fetch is an observation, never a flag)
    NEVER from a failed check (see check_is_valid): CHECK_FAILED blocks
    are skipped entirely.

    Rationale: sentier-…-glieres is flagged Google "permanently closed"
    because Google doesn't classify hiking trails as businesses, not
    because the path was removed. train-du-montenvers shows
    site_reachable=False but is in active service. Auto-demoting on
    those signals would silently remove operational venues.
    """
    fr = d.get("freshness") or {}
    gc = d.get("google_check") or {}
    # a freshness block whose google_status is ERROR was written from a
    # failed call under the pre-HANDOFF-24 scripts — same discipline applies
    fr_valid = check_is_valid(fr) and fr.get("google_status") != "ERROR"
    gc_valid = check_is_valid(gc)
    if not fr_valid:
        fr = {}
    if not gc_valid:
        gc = {}
    fr_status = fr.get("status")
    gc_status = gc.get("status")
    confidence = fr.get("confidence")

    if fr_status == "CLOSED" and confidence == "high":
        return "demote", f"freshness: CLOSED (high confidence, checked {fr.get('checked', '?')}); reason={fr.get('flag_reason', '?')}"

    # All other negative signals → flag, never auto-demote.
    if fr_status == "CLOSED":
        return "flag", f"freshness: CLOSED ({confidence or 'no'} confidence, checked {fr.get('checked', '?')}); reason={fr.get('flag_reason', '?')}"
    if gc_status == "CLOSED_PERMANENTLY":
        return "flag", f"google_check: CLOSED_PERMANENTLY (checked {gc.get('checked', '?')}) — Google-only signal, manual review"
    if gc_status == "NOT_A_BUSINESS":
        return "flag", f"google_check: NOT_A_BUSINESS (checked {gc.get('checked', '?')}) — often a Google classifier quirk for trails/paths"
    if gc_status == "CLOSED_TEMPORARILY":
        return "flag", f"google_check: CLOSED_TEMPORARILY (checked {gc.get('checked', '?')}) — could be seasonal"
    if fr.get("site_reachable") is False and fr.get("site_unreachable_confirmed"):
        return "flag", (f"freshness: official site not responding, confirmed by a second "
                        f"failed fetch on a later day (checked {fr.get('checked', '?')})")
    return None, None


MASS_SIGNAL_LIMIT = 0.10  # >10% of fiches demoted+flagged in one run = broken checker


def apply(args):
    demoted = []
    flagged = []
    skipped = []  # already-draft fiches we don't touch
    upgraded_count = 0
    paths = sorted(JSON_DIR.glob("*.json"))

    # Phase 1 — collect every action IN MEMORY. Nothing is written until the
    # run passes the mass-signal breaker: if >10% of the catalog throws
    # negative signals on the same run, the checker is broken, not the world
    # (2026-07-01: 42 same-day "site down" flags incl. Pathé Annecy).
    to_write = []
    for jp in paths:
        d = json.loads(jp.read_text(encoding="utf-8"))
        slug = d.get("slug") or jp.stem
        action, reason = signal_for(d)
        cur_status = d.get("status", "published")

        if action == "demote":
            if cur_status == "draft":
                skipped.append((slug, reason)); continue
            demoted.append((slug, cur_status, reason))
            to_write.append((jp, d, reason))
        elif action == "flag":
            flagged.append((slug, reason))

    if paths and (len(demoted) + len(flagged)) / len(paths) > MASS_SIGNAL_LIMIT:
        print(f"\n🔴 MASS-SIGNAL BREAKER: {len(demoted)} demotions + {len(flagged)} flags "
              f"across {len(paths)} fiches (> {int(MASS_SIGNAL_LIMIT*100)}% limit).")
        print("That many same-run negative signals means the checkers are broken,")
        print("not the venues. ZERO fiches were written. Investigate the sweep first.")
        sys.exit(2)

    # Phase 2 — breaker passed: write the demotions.
    if not args.dry_run:
        for jp, d, reason in to_write:
            d["status"] = "draft"
            rl = d.setdefault("research_log", [])
            rl.append({
                "date": TODAY,
                "by": "scripts/apply_sweep_signals.py",
                "note": f"Demoted to draft. {reason}",
            })
            jp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return demoted, flagged, skipped, upgraded_count


def simulate_dead_venue(slug):
    """Inject a synthetic high-confidence CLOSED signal into <slug>.json so the
    end-to-end demotion path can be gate-tested."""
    jp = JSON_DIR / f"{slug}.json"
    if not jp.exists():
        raise SystemExit(f"no such fiche: {slug}")
    d = json.loads(jp.read_text(encoding="utf-8"))
    d.setdefault("freshness", {})
    d["freshness"]["status"] = "CLOSED"
    d["freshness"]["confidence"] = "high"
    d["freshness"]["checked"] = TODAY
    d["freshness"]["flag_reason"] = "synthetic test signal (apply_sweep_signals --simulate-dead-venue)"
    d.setdefault("google_check", {})
    d["google_check"]["status"] = "CLOSED_PERMANENTLY"
    d["google_check"]["checked"] = TODAY
    jp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  injected high-confidence CLOSED → {slug}")


def restore_test_signal(slug):
    """Undo simulate_dead_venue: remove synthetic CLOSED markers."""
    jp = JSON_DIR / f"{slug}.json"
    if not jp.exists():
        raise SystemExit(f"no such fiche: {slug}")
    d = json.loads(jp.read_text(encoding="utf-8"))
    fr = d.get("freshness") or {}
    if "synthetic test signal" in (fr.get("flag_reason") or ""):
        fr["status"] = "OPERATIONAL"
        fr["confidence"] = "high"
        fr["flag_reason"] = ""
    gc = d.get("google_check") or {}
    if gc.get("status") == "CLOSED_PERMANENTLY" and gc.get("checked") == TODAY:
        gc["status"] = "OPERATIONAL"
    # also un-demote
    if d.get("status") == "draft":
        d["status"] = "published"
        rl = d.get("research_log") or []
        rl = [r for r in rl if "apply_sweep_signals.py" not in (r.get("by") or "")
              and "synthetic" not in (r.get("note") or "").lower()]
        d["research_log"] = rl
    jp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  restored {slug} (status, freshness, google_check)")


def write_report(demoted, flagged, skipped):
    out = ["# JOB 8 — Sweep signals → state machine\n"]
    out.append(f"Run at {TODAY}. Source signals: `freshness` (sweep_loisirs74.py) + "
               "`google_check` (check_loisirs74.py).\n\n")
    out.append("## Summary\n\n")
    out.append(f"| action | count |\n|---|---|\n")
    out.append(f"| demoted to draft (new) | {len(demoted)} |\n")
    out.append(f"| flagged for review (kept published) | {len(flagged)} |\n")
    out.append(f"| skipped (already draft) | {len(skipped)} |\n\n")

    if demoted:
        out.append("## Demoted\n\n")
        out.append("| slug | previous status | reason |\n|---|---|---|\n")
        for slug, prev, reason in demoted:
            out.append(f"| {slug} | {prev} | {reason} |\n")
        out.append("\n")
    if flagged:
        out.append("## Flagged for review (kept published — seasonal / temporary signals)\n\n")
        out.append("| slug | reason |\n|---|---|\n")
        for slug, reason in flagged:
            out.append(f"| {slug} | {reason} |\n")
        out.append("\n")

    (ROOT / "reports" / "job8-sweep-demotions.md").write_text("".join(out), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change without writing")
    ap.add_argument("--simulate-dead-venue", metavar="SLUG",
                    help="Inject a synthetic high-confidence CLOSED signal for end-to-end gate test")
    ap.add_argument("--restore", metavar="SLUG",
                    help="Undo a previous --simulate-dead-venue on SLUG (restore status=published, OPERATIONAL)")
    args = ap.parse_args()

    if args.restore:
        restore_test_signal(args.restore)
    if args.simulate_dead_venue:
        simulate_dead_venue(args.simulate_dead_venue)

    demoted, flagged, skipped, _ = apply(args)
    if not args.dry_run:
        write_report(demoted, flagged, skipped)

    print(f"demoted to draft: {len(demoted)}  (was published or verified)")
    for slug, prev, reason in demoted:
        print(f"  - {slug}  [{prev}]  {reason}")
    print(f"flagged for review (kept published): {len(flagged)}")
    print(f"skipped (already draft): {len(skipped)}")
    if args.dry_run:
        print("(dry-run — no JSON and no report was written)")
    else:
        print(f"\nReport: reports/job8-sweep-demotions.md")


if __name__ == "__main__":
    main()
