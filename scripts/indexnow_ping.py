#!/usr/bin/env python3
"""indexnow_ping.py — manual IndexNow submitter (HANDOFF-33). NEVER a cron.

Pushes URLs to https://api.indexnow.org/indexnow (fans out to Bing, Seznam,
Naver, Yandex, …). Google ignores IndexNow — the GSC sitemap path is separate
and untouched.

THE RULE: nothing is sent without a human running this by hand with --send.
Without --send every mode is a dry run: it prints the URL count + the first
10 URLs and sends NOTHING. There is no schedule, no deploy hook, no cron —
the bell is wired to the door; nobody rings it but the Edmaster.

Scopes (exactly one):
  --all          every URL in the sitemap
  --lang xx      only that language's tree from the sitemap (fr = the
                 unprefixed URLs)
  --urls FILE    explicit list, one URL per line (# comments allowed)

Options:
  --send         actually POST (otherwise: dry run, prints and exits)
  --sitemap SRC  sitemap source — a URL or a local path
                 (default: https://loisirs74.fr/sitemap.xml, the LIVE truth)

Every real send is appended to reports/indexnow-pings.json:
  {date, mode, count, status} — deliberate, auditable, repeatable.

Examples:
  python3 scripts/indexnow_ping.py --all                    # dry run, free
  python3 scripts/indexnow_ping.py --lang pt --send         # fire pt tree
  python3 scripts/indexnow_ping.py --urls one.txt --send    # fire a list
"""
import argparse
import siteconfig  # HANDOFF-73: per-site identity
import datetime
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locales  # noqa: E402

HOST = siteconfig.DOMAIN
KEY = "5a95126a64e5a8af65889718abd8029b"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
DEFAULT_SITEMAP = f"https://{HOST}/sitemap.xml"
LOG = os.path.join(ROOT, "reports", "indexnow-pings.json")
BATCH = 10_000   # IndexNow per-POST ceiling

LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def load_sitemap(src):
    if re.match(r"^https?://", src):
        with urllib.request.urlopen(src, timeout=30) as r:
            xml = r.read().decode("utf-8", "replace")
    else:
        xml = open(src, encoding="utf-8").read()
    urls = LOC_RE.findall(xml)
    if not urls:
        sys.exit(f"no <loc> URLs found in sitemap {src!r}")
    return urls


def filter_lang(urls, lang):
    if lang == "fr":
        prefixes = tuple(f"https://{HOST}/{lg}/" for lg in locales.ALL_SUBDIR_LANGS)
        return [u for u in urls if not u.startswith(prefixes)]
    return [u for u in urls if u.startswith(f"https://{HOST}/{lang}/")]


def post(urls):
    payload = json.dumps({
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls,
    }).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def log_send(mode, count, statuses):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    entries = []
    if os.path.exists(LOG):
        entries = json.loads(open(LOG, encoding="utf-8").read())
    entries.append({
        "date": datetime.datetime.now(datetime.timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": mode,
        "count": count,
        "status": statuses if len(statuses) > 1 else statuses[0],
    })
    with open(LOG, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=1)
    print(f"logged -> {os.path.relpath(LOG, ROOT)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    scope = ap.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="every sitemap URL")
    scope.add_argument("--lang", help="one language tree from the sitemap")
    scope.add_argument("--urls", help="file with one URL per line")
    ap.add_argument("--send", action="store_true",
                    help="actually POST (default is a dry run that sends nothing)")
    ap.add_argument("--sitemap", default=DEFAULT_SITEMAP,
                    help="sitemap source (URL or local path)")
    args = ap.parse_args()

    if args.urls:
        mode = f"urls:{os.path.basename(args.urls)}"
        urls = [l.strip() for l in open(args.urls, encoding="utf-8")
                if l.strip() and not l.startswith("#")]
    else:
        sm = load_sitemap(args.sitemap)
        if args.lang:
            if args.lang != "fr" and args.lang not in locales.ALL_SUBDIR_LANGS:
                sys.exit(f"unknown language {args.lang!r}")
            mode = f"lang:{args.lang}"
            urls = filter_lang(sm, args.lang)
        else:
            mode = "all"
            urls = sm
    if not urls:
        sys.exit(f"scope {mode!r} matched 0 URLs — nothing to do")

    bad = [u for u in urls if not u.startswith(f"https://{HOST}/") and u != f"https://{HOST}/"]
    if bad:
        sys.exit(f"{len(bad)} URL(s) outside https://{HOST}/ — refusing (first: {bad[0]!r})")

    print(f"indexnow_ping [{mode}]: {len(urls)} URL(s); first 10:")
    for u in urls[:10]:
        print("   ", u)

    if not args.send:
        print("DRY RUN — nothing sent. Add --send to fire (Edmaster's word only).")
        return

    statuses = []
    for i in range(0, len(urls), BATCH):
        chunk = urls[i:i + BATCH]
        status = post(chunk)
        statuses.append(status)
        print(f"POST {ENDPOINT} [{i + 1}-{i + len(chunk)}] -> HTTP {status}")
    log_send(mode, len(urls), statuses)
    if any(s not in (200, 202) for s in statuses):
        sys.exit("::error::IndexNow returned a non-200/202 status — see log")
    print(f"✓ {len(urls)} URL(s) submitted to IndexNow (HTTP {statuses})")


if __name__ == "__main__":
    main()
