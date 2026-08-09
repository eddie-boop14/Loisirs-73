#!/usr/bin/env python3
"""assets.py — content-hash versioning for runtime /scripts/ includes (HANDOFF-12).

The single place that turns a bare `/scripts/<file>.js` include into a
cache-busted `/scripts/<file>.js?v=<hash>`. The hash is derived from the file's
own bytes, so any future edit to the asset changes the URL and every client
fetches fresh — automatically, no manual bump. Paired with the `/scripts/*`
`immutable` rule in `_headers`, this makes runtime JS both long-cached AND
never-stale (the duck speaking French on the EN page was a v1 cache that never
refreshed).

Two entry points:
  script_tag(name, defer=True)  -> a fresh, versioned <script> include (emitters)
  stamp(html)                   -> rewrite EVERY runtime include already in a page
                                   to the current hash, idempotently (the sitewide
                                   pass; also re-stamps committed homepages whose
                                   includes no builder re-emits).
"""
import hashlib
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The runtime client scripts that ship to /scripts/ (build_site RUNTIME_JS).
RUNTIME = ("duck.js", "nearme.js", "l74sort.js")


def asset_version(name):
    """Short content hash of scripts/<name>."""
    with open(os.path.join(ROOT, "scripts", name), "rb") as fh:
        return hashlib.sha1(fh.read()).hexdigest()[:10]


# computed once per process (the asset bytes don't change mid-build)
VERSIONS = {n: asset_version(n) for n in RUNTIME}


def script_tag(name, defer=True):
    d = " defer" if defer else ""
    return f'<script src="/scripts/{name}?v={VERSIONS[name]}"{d}></script>'


# rewrite `src="/scripts/<runtime>.js"` (with or without an existing ?v=) to the
# current hash. Anchored on src=" so nothing but a real include is touched.
_STAMP_RE = re.compile(
    r'(src=")/scripts/(' + "|".join(re.escape(n) for n in RUNTIME) + r')(?:\?v=[A-Za-z0-9]+)?(")'
)


def stamp(html):
    return _STAMP_RE.sub(lambda m: f'{m.group(1)}/scripts/{m.group(2)}?v={VERSIONS[m.group(2)]}{m.group(3)}', html)
