#!/usr/bin/env python3
"""migrate_status.py — JOB 6 migration. Add an explicit `status` field to
every fiche, replacing the implicit "render-everyone" rule with a proper
state machine: draft / verified / published.

Rule (this round):
  - status = "draft" if sparse_data is True (skeleton fiches; content is
    explicitly marked incomplete) OR if name/meta_title is missing
  - status = "published" otherwise (the default, preserves current
    rendering behavior)
  - "verified" is reserved for JOB 8's freshness sweep to use later
    (intermediate state between data-ingest and ready-to-ship)

build_all only renders fiches with status == "published":
  - draft fiches: skipped by build_all_locales (no HTML written)
  - draft fiches: omitted from catalog-index.json + lieux.json
  - draft fiches: omitted from sitemap.xml
  - draft fiches: omitted from hubs
  - draft fiches: omitted from _site/Json/

Idempotent. Re-running with the same rule produces no changes.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def derive_status(d):
    """Return the canonical status for fiche d.

    The initial migration is purely additive: every fiche that is currently
    shipping becomes "published". Draft is reserved for explicit future
    demotions (JOB 8 freshness sweep finds a dead venue, an audit demotes
    on a Tier-1 hit, etc.). Verified is reserved for the intermediate
    QA state JOB 8 may use.

    Hard draft criterion this round: missing canonical name. Doesn't match
    any current fiche, but the rule is in place so JOB 8 can demote.

    `sparse_data` is NOT used as a draft signal — it's an early-import
    marker that was never cleared even when fiches got fully enriched;
    treating it as draft would silently delete content-complete fiches.
    Stale sparse_data flags are cleared by clear_stale_sparse_data().
    """
    fr = (d.get("i18n", {}) or {}).get("fr") or {}
    name = fr.get("name")
    if not name or len(str(name).strip()) < 3:
        return "draft"
    return "published"


def clear_stale_sparse_data(d):
    """If sparse_data=True but body content is substantial, clear the flag.
    Returns True if d was modified."""
    if d.get("sparse_data") is not True:
        return False
    fr = (d.get("i18n", {}) or {}).get("fr") or {}
    body = fr.get("body") if isinstance(fr.get("body"), dict) else {}
    wi = body.get("what_is") or fr.get("what_is") or ""
    if isinstance(wi, str) and len(wi) >= 800:
        d["sparse_data"] = False
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print would-be changes without writing")
    args = ap.parse_args()

    changed = 0
    sparse_cleared = 0
    dist = Counter()
    for jp in sorted((ROOT / "Json").glob("*.json")):
        d = json.loads(jp.read_text(encoding="utf-8"))
        mod = False
        if clear_stale_sparse_data(d):
            sparse_cleared += 1
            mod = True
        new_status = derive_status(d)
        cur_status = d.get("status")
        if cur_status != new_status:
            d["status"] = new_status
            mod = True
            if cur_status is None:
                print(f"  set {jp.stem}: status → {new_status}")
            else:
                print(f"  update {jp.stem}: {cur_status} → {new_status}")
        if mod and not args.dry_run:
            jp.write_text(
                json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8"
            )
            changed += 1
        dist[new_status] += 1

    print(f"\nfiches changed: {changed}")
    print(f"stale sparse_data flags cleared: {sparse_cleared}")
    print(f"\nstatus distribution:")
    for s, n in dist.most_common():
        print(f"  {s}: {n}")

    # Write distribution report
    if not args.dry_run:
        report = {
            "total": sum(dist.values()),
            "by_status": dict(dist),
            "rule": "draft if sparse_data=True OR missing name; published otherwise; verified reserved for JOB 8 sweep",
            "draft_slugs": sorted(jp.stem for jp in (ROOT / "Json").glob("*.json")
                                  if json.loads(jp.read_text(encoding="utf-8")).get("status") == "draft"),
        }
        (ROOT / "scripts" / "job6-status-distribution.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nReport: scripts/job6-status-distribution.json")


if __name__ == "__main__":
    main()
