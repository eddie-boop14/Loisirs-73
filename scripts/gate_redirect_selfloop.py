#!/usr/bin/env python3
"""Redirect self-loop gate — the 2026-08-19 tripwire.

Read-only, and it reads NOTHING but `_redirects`. That independence is the
whole point: the sibling gate `gate_redirect_shadows` can only see a bad rule
when the target page happens to exist in the built tree. This one sees the rule
itself.

WHAT IT FORBIDS
---------------
Netlify matches a request path to a rule *regardless of whether the path has a
trailing slash*:

    "Netlify will match paths to rules regardless of whether or not they
     contain a trailing slash."
    "You cannot use a redirect rule to add or remove trailing slashes.
     Attempting to do so causes infinite redirects."
    — docs.netlify.com/manage/routing/redirects/redirect-options

So `/x/` and `/x` are ONE rule at the edge. Any rule whose source and target
are equal once trailing slashes are stripped therefore points at itself:

    /cascade-du-morel/   /cascade-du-morel   301!    <- self-loop
    /cascade-du-morel    /cascade-du-morel/  301!    <- self-loop, either way
    /x/                  /x                  301     <- self-loop when no file
                                                        matches; unforced only
                                                        defers the loop, it
                                                        does not prevent it

On 2026-08-19, 816 rules of the first shape shipped with all 33 gates green and
took every fiche on loisirs73.fr off the internet — 129 lieux × 12 locales,
ERR_TOO_MANY_REDIRECTS, on the canonical URL as much as the phantom. They were
also redundant: Netlify already collapses `/x/` onto `/x` natively, which is
the outcome the rules were written to produce.

The predicate here is deliberately narrow and purely syntactic — source and
target differing only by a trailing slash — because that is the property that
can be decided from the file alone, with no build, no network, and no
assumption about what the platform does with slashes beyond the sentence quoted
above. It cannot go green on a broken tree the way a tree-dependent check can.

Absolute targets on another host are skipped (they are somebody else's loop).
Absolute targets on our own host are normalised to their path and checked.

Usage: python3 scripts/gate_redirect_selfloop.py [--redirects FILE]
Exit 0 = clean · exit 1 = at least one self-loop.

2026 · Bleu canard édition · Edmaster & Claudius · Tous droits réservés
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF_HOSTS = ("loisirs73.fr", "www.loisirs73.fr")
STATUS_RE = re.compile(r"^\d{3}!?$")


def norm(path):
    """Collapse a rule path to the form Netlify matches on.

    Trailing slash is stripped because the edge ignores it. Query strings and
    fragments are dropped: they do not participate in path matching. The root
    `/` normalises to `/` and never to the empty string.
    """
    path = path.split("#", 1)[0].split("?", 1)[0]
    for host in SELF_HOSTS:
        for scheme in ("https://", "http://"):
            if path.lower().startswith(scheme + host):
                path = path[len(scheme + host):] or "/"
                break
    if path.startswith("http://") or path.startswith("https://"):
        return None                      # another host — not our loop
    if path.startswith("//"):
        return None                      # protocol-relative — another host
    stripped = path.rstrip("/")
    return stripped if stripped else "/"


def parse(path):
    """Yield (lineno, source, target, status, forced) for every redirect rule."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            s = line.split("#", 1)[0].strip()
            if not s:
                continue
            parts = s.split()
            if len(parts) < 2:
                continue
            status, forced = "301", False   # Netlify's default when omitted
            if len(parts) >= 3 and STATUS_RE.match(parts[2]):
                forced = parts[2].endswith("!")
                status = parts[2].rstrip("!")
            out.append((i, parts[0], parts[1], status, forced))
    return out


def main():
    ap = argparse.ArgumentParser(
        description="No _redirects rule may point at itself modulo a trailing slash.")
    ap.add_argument("--redirects", default=os.path.join(ROOT, "_redirects"))
    args = ap.parse_args()

    if not os.path.isfile(args.redirects):
        print(f"::error::no _redirects at {args.redirects}", file=sys.stderr)
        return 1

    rules = parse(args.redirects)
    loops = []
    for lineno, src, dst, status, forced in rules:
        if not status.startswith("3"):
            continue                     # 200 rewrites and 404s are not loops
        a, b = norm(src), norm(dst)
        if a is None or b is None:
            continue                     # off-host
        if a == b:
            loops.append((lineno, src, dst, status, forced))

    print(f"gate_redirect_selfloop: {len(rules)} rule(s) parsed, "
          f"{sum(1 for r in rules if r[3].startswith('3'))} redirect(s) checked")
    if not loops:
        print("✓ no rule redirects to itself modulo a trailing slash")
        return 0

    forced_n = sum(1 for L in loops if L[4])
    print(f"::error::{len(loops)} self-redirect(s) — {forced_n} forced. "
          f"Netlify ignores the trailing slash when matching, so each of these "
          f"sends a URL to itself forever:")
    for lineno, src, dst, status, forced in loops:
        bang = "!" if forced else ""
        note = "  <- forced: loops even where a real page exists" if forced else ""
        print(f"    ✗ _redirects:{lineno}  {src}  {dst}  {status}{bang}{note}")
    print("\n  Netlify already collapses /x/ onto /x natively. A rule of this "
          "shape is never the fix; delete it.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # `... | head` closes the pipe early; that is not a gate failure, but
        # the violation list is long enough that it will be piped.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(1)
