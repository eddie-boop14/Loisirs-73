"""Per-site identity — read from site.config.json at the repo root.

HANDOFF-73 phase 1 (2026-08-05): the engine/content split starts here. Every
engine script that needs the domain, base URL, site name, department or beacon
token imports THIS module instead of hardcoding a literal. site.config.json is
the only file that changes between loisirs74.fr and the next département.

Contract:
- Fail loudly if the file is missing or a key is absent — a template engine
  that silently falls back to '74' values would poison a '73' deploy.
- Values are plain constants at import time; builders keep their existing
  local names (BASE, BASE_URL) assigned from here, so call sites don't churn.
"""
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CFG_PATH = _ROOT / "site.config.json"

try:
    _cfg = json.loads(_CFG_PATH.read_text(encoding="utf-8"))
except FileNotFoundError as e:  # pragma: no cover
    raise SystemExit(
        f"siteconfig: {_CFG_PATH} is missing — the engine has no identity. "
        "Copy site.config.json from a sibling site and edit it."
    ) from e

def _req(key):
    v = _cfg.get(key)
    if v in (None, ""):
        raise SystemExit(f"siteconfig: required key '{key}' missing in {_CFG_PATH}")
    return v

DOMAIN = _req("domain")                      # loisirs74.fr
BASE_URL = _req("base_url").rstrip("/")      # https://loisirs74.fr  (no trailing slash)
SITE_NAME = _req("site_name")                # Loisirs 74
DEPARTMENT = _req("department")              # {"code": "74", "name": "Haute-Savoie"}
DEPT_CODE = DEPARTMENT["code"]
DEPT_NAME = DEPARTMENT["name"]
DEPT_NAME_I18N = DEPARTMENT.get("name_i18n") or {}


def dept_name(lang):
    """Department name in `lang`, falling back to the French form.

    The 74 renders "Alta Savoia" in Italian and "Alta Saboya" in Spanish but
    keeps "Haute-Savoie" elsewhere, so the name cannot be a single constant.
    A site that freezes the French form in every language simply omits
    department.name_i18n and every language falls back to DEPT_NAME.
    """
    return DEPT_NAME_I18N.get(lang, DEPT_NAME)
IMPRINT = _req("imprint")
CONTACT_EMAIL = _req("contact_email")
PHOTOS_EMAIL = _req("photos_email")
CF_BEACON_TOKEN = _cfg.get("cf_beacon_token", "")
REGION = _cfg.get("region", "")
ANCHOR_CITY = _cfg.get("anchor_city", "")

# Department envelope (S, W, N, E) — used by the Overpass and feed builders to
# pre-filter national datasets down to this site's ground. Hardcoding it means a
# new departement silently indexes its neighbour's car parks.
_bb = _cfg.get("bbox") or {}
BBOX = ((_bb.get("south"), _bb.get("west"), _bb.get("north"), _bb.get("east"))
        if _bb else None)
ADJACENT_SCOPE_NOTE = _cfg.get("adjacent_scope_note", "")

# Optional sibling site. Absent = no cross-link rendered anywhere. See
# build_lieu_page.sister_link_html() for why this stays off until the sibling
# actually resolves.
SISTER = _cfg.get("sister") or None

# Regex-safe forms. Engine scripts parse their OWN rendered HTML looking for
# site URLs; those patterns must be built from the configured domain, never
# from a literal. Kept as constants so call sites concatenate rather than
# f-string — several of those patterns contain {n} quantifiers.
import re as _re

DOMAIN_RE = _re.escape(DOMAIN)                 # loisirs74\.fr
SITE_URL_RE = "https://" + DOMAIN_RE           # https://loisirs74\.fr
SITE_NAME_RE = _re.escape(SITE_NAME)           # Loisirs\ 74
WORDMARK = DOMAIN.split(".")[0]                # loisirs74

