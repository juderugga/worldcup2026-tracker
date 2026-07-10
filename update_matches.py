#!/usr/bin/env python3
"""
WC2026 Match Data Auto-Updater
Sources match data from ESPN's public API and updates matchdata.json.

What it does:
  - Adds stats (possession, shots, corners, fouls) to existing entries missing them
  - Creates full new entries for matches not yet in matchdata.json
  - Never overwrites fields that already have data (manual edits are preserved)

Run daily; idempotent (safe to run multiple times).
"""

import json
import os
import re
import time
import requests

MATCHDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "matchdata.json")
ESPN_SUMMARY  = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={}"
ESPN_BOARD    = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={}"

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0"}

# Known ESPN event IDs for group-stage round 1 matches
# Groups A-L (12 groups total in WC2026):
#   A: Mexico, South Korea, South Africa, Czechia
#   B: Canada, Bosnia-Herzegovina, Switzerland, Qatar
#   C: Brazil, Scotland, Haiti, Morocco
#   D: Paraguay, Türkiye, Australia, United States
#   E: Ecuador, Germany, Ivory Coast, Curaçao
#   F: Netherlands, Sweden, Japan, Tunisia
#   G: Belgium, Iran, Egypt, New Zealand
#   H: Spain, Uruguay, Saudi Arabia, Cape Verde
#   I: Norway, France, Senegal, Iraq
#   J: Argentina, Austria, Algeria, Jordan
#   K: Colombia, Portugal, Uzbekistan, Congo DR
#   L: England, Croatia, Panama, Ghana
KNOWN_IDS = {
    # Group stage – Round 1
    "A1": "760415",   # Mexico vs South Africa
    "A2": "760414",   # South Korea vs Czechia
    "B1": "760416",   # Canada vs Bosnia-Herzegovina
    "B2": "760420",   # Qatar vs Switzerland
    "C1": "760419",   # Brazil vs Morocco
    "C2": "760418",   # Haiti vs Scotland
    "D1": "760417",   # United States vs Paraguay
    "D2": "760421",   # Australia vs Türkiye
    "E1": "760423",   # Ivory Coast vs Ecuador
    "E2": "760422",   # Germany vs Curaçao
    "F1": "760425",   # Netherlands vs Japan
    "F2": "760424",   # Sweden vs Tunisia
    "G1": "760427",   # Iran vs New Zealand
    "G2": "760426",   # Belgium vs Egypt
    "H1": "760429",   # Saudi Arabia vs Uruguay
    "H2": "760428",   # Spain vs Cape Verde
    "I1": "760432",   # France vs Senegal
    "I2": "760430",   # Iraq vs Norway
    "J1": "760433",   # Argentina vs Algeria
    "J2": "760431",   # Austria vs Jordan
    "K1": "760435",   # Portugal vs Congo DR
    # Round of 32 (knockout stage) — keyed by BRACKET SLOT, not play date
    "R32_1": "760486",  # 2nd A v 2nd B — South Africa vs Canada (Jun 28)
    "R32_2": "760489",  # 1st E v 3rd  — Germany vs Paraguay (Jun 29)
    "R32_3": "760488",  # 1st F v 2nd C — Netherlands vs Morocco (Jun 29)
    "R32_4": "760487",  # 1st C v 2nd F — Brazil vs Japan (Jun 29)
}

# Position abbreviation mapping: ESPN abbrev → our lineup prefix
POS_MAP = {
    "G":    "GK",
    "CD":   "CB", "CD-L": "CB", "CD-R": "CB",
    "LB":   "LB", "RB":   "RB",
    "LWB":  "LWB", "RWB": "RWB",
    "DM":   "DM",
    "CM":   "CM", "CM-L": "CM", "CM-R": "CM",
    "AM":   "CAM", "AM-L": "CAM", "AM-R": "CAM",
    "LM":   "LM", "RM":   "RM",
    "LW":   "LW", "RW":   "RW",
    "F":    "ST", "CF":   "ST", "CF-L": "FW", "CF-R": "FW",
    "SS":   "CAM",  # second striker / shadow
}

# ── Full group-stage fixture schedule, keyed by our match id ──
# (home, away) in the SAME order the tracker page expects.
# Used to map ESPN-discovered matches onto real fixture keys (A3, C4, …)
# instead of placeholder NEW# keys, so results show up on the tracker.
FIXTURE_SCHEDULE = {
    "A1": ("Mexico", "South Africa"),        "A2": ("South Korea", "Czechia"),
    "A3": ("Czechia", "South Africa"),       "A4": ("Mexico", "South Korea"),
    "A5": ("Czechia", "Mexico"),             "A6": ("South Africa", "South Korea"),
    "B1": ("Canada", "Bosnia and Herzegovina"), "B2": ("Qatar", "Switzerland"),
    "B3": ("Switzerland", "Bosnia and Herzegovina"), "B4": ("Canada", "Qatar"),
    "B5": ("Switzerland", "Canada"),         "B6": ("Bosnia and Herzegovina", "Qatar"),
    "C1": ("Brazil", "Morocco"),             "C2": ("Haiti", "Scotland"),
    "C3": ("Scotland", "Morocco"),           "C4": ("Brazil", "Haiti"),
    "C5": ("Scotland", "Brazil"),            "C6": ("Morocco", "Haiti"),
    "D1": ("United States", "Paraguay"),     "D2": ("Australia", "Türkiye"),
    "D3": ("Türkiye", "Paraguay"),           "D4": ("United States", "Australia"),
    "D5": ("Türkiye", "United States"),      "D6": ("Paraguay", "Australia"),
    "E1": ("Ivory Coast", "Ecuador"),        "E2": ("Germany", "Curaçao"),
    "E3": ("Germany", "Ivory Coast"),        "E4": ("Ecuador", "Curaçao"),
    "E5": ("Curaçao", "Ivory Coast"),        "E6": ("Ecuador", "Germany"),
    "F1": ("Netherlands", "Japan"),          "F2": ("Sweden", "Tunisia"),
    "F3": ("Netherlands", "Sweden"),         "F4": ("Tunisia", "Japan"),
    "F5": ("Japan", "Sweden"),               "F6": ("Tunisia", "Netherlands"),
    "G1": ("Iran", "New Zealand"),           "G2": ("Belgium", "Egypt"),
    "G3": ("Belgium", "Iran"),               "G4": ("New Zealand", "Egypt"),
    "G5": ("Egypt", "Iran"),                 "G6": ("New Zealand", "Belgium"),
    "H1": ("Saudi Arabia", "Uruguay"),       "H2": ("Spain", "Cape Verde"),
    "H3": ("Uruguay", "Cape Verde"),         "H4": ("Spain", "Saudi Arabia"),
    "H5": ("Cape Verde", "Saudi Arabia"),    "H6": ("Uruguay", "Spain"),
    "I1": ("France", "Senegal"),             "I2": ("Iraq", "Norway"),
    "I3": ("Norway", "Senegal"),             "I4": ("France", "Iraq"),
    "I5": ("Norway", "France"),              "I6": ("Senegal", "Iraq"),
    "J1": ("Argentina", "Algeria"),          "J2": ("Austria", "Jordan"),
    "J3": ("Argentina", "Austria"),          "J4": ("Jordan", "Algeria"),
    "J5": ("Algeria", "Austria"),            "J6": ("Jordan", "Argentina"),
    "K1": ("Portugal", "DR Congo"),          "K2": ("Uzbekistan", "Colombia"),
    "K3": ("Portugal", "Uzbekistan"),        "K4": ("Colombia", "DR Congo"),
    "K5": ("Colombia", "Portugal"),          "K6": ("DR Congo", "Uzbekistan"),
    "L1": ("Ghana", "Panama"),               "L2": ("England", "Croatia"),
    "L3": ("England", "Ghana"),              "L4": ("Panama", "Croatia"),
    "L5": ("Panama", "England"),             "L6": ("Croatia", "Ghana"),
}

# ESPN spells a few nations differently than the tracker — normalise to match.
NAME_ALIASES = {
    "bosnia-herzegovina": "bosnia and herzegovina",
    "congo dr": "dr congo",
    "ir iran": "iran",
    "korea republic": "south korea",
    "republic of ireland": "ireland",
}

def norm_team(name):
    n = (name or "").strip().lower()
    return NAME_ALIASES.get(n, n)

# Lookup: frozenset of the two normalised names -> fixture key
FIXTURE_LOOKUP = {
    frozenset((norm_team(h), norm_team(a))): k
    for k, (h, a) in FIXTURE_SCHEDULE.items()
}

# Canonical display name for each normalised team name (tracker spelling)
CANON = {}
for _h, _a in FIXTURE_SCHEDULE.values():
    CANON[norm_team(_h)] = _h
    CANON[norm_team(_a)] = _a

# ── Knockout bracket slots, matching the tracker page exactly ──
# key -> (match label, home ref, away ref). Refs are placeholders like
# "1st A", "2nd B", "3rd A/B/C/D/F", "W M73", "L SF1".
KO_SLOTS = {
    "R32_1":  ("M73", "2nd A", "2nd B"),
    "R32_2":  ("M74", "1st E", "3rd A/B/C/D/F"),
    "R32_3":  ("M75", "1st F", "2nd C"),
    "R32_4":  ("M76", "1st C", "2nd F"),
    "R32_5":  ("M77", "1st I", "3rd C/D/F/G/H"),
    "R32_6":  ("M78", "2nd E", "2nd I"),
    "R32_7":  ("M79", "1st A", "3rd C/E/F/H/I"),
    "R32_8":  ("M80", "1st L", "3rd E/H/I/J/K"),
    "R32_9":  ("M81", "1st D", "3rd B/E/F/I/J"),
    "R32_10": ("M82", "1st G", "3rd A/E/H/I/J"),
    "R32_11": ("M83", "2nd K", "2nd L"),
    "R32_12": ("M84", "1st H", "2nd J"),
    "R32_13": ("M85", "1st B", "3rd E/F/G/I/J"),
    "R32_14": ("M86", "1st J", "2nd H"),
    "R32_15": ("M87", "1st K", "3rd D/E/I/J/L"),
    "R32_16": ("M88", "2nd D", "2nd G"),
    "R16_1":  ("M89", "W M74", "W M77"),
    "R16_2":  ("M90", "W M73", "W M75"),
    "R16_3":  ("M91", "W M76", "W M78"),
    "R16_4":  ("M92", "W M79", "W M80"),
    "R16_5":  ("M93", "W M83", "W M84"),
    "R16_6":  ("M94", "W M81", "W M82"),
    "R16_7":  ("M95", "W M86", "W M88"),
    "R16_8":  ("M96", "W M85", "W M87"),
    "QF1":    ("QF1", "W M89", "W M90"),
    "QF2":    ("QF2", "W M93", "W M94"),
    "QF3":    ("QF3", "W M91", "W M92"),
    "QF4":    ("QF4", "W M95", "W M96"),
    "SF1":    ("SF1", "W QF1", "W QF2"),
    "SF2":    ("SF2", "W QF3", "W QF4"),
    "3P1":    ("3P1", "L SF1", "L SF2"),
    "FIN":    ("FIN", "W SF1", "W SF2"),
}
LABEL_TO_KEY = {label: key for key, (label, _, _) in KO_SLOTS.items()}


def compute_standings(data):
    """Group tables from stored results. Returns {group: (ranked normalised
    team names, complete?)} using pts > GD > GF > name (same as the tracker)."""
    res = {}
    for gid in "ABCDEFGHIJKL":
        stats = {}
        for n in range(1, 7):
            k = f"{gid}{n}"
            h, a = FIXTURE_SCHEDULE[k]
            for t in (h, a):
                stats.setdefault(t, {"p": 0, "gf": 0, "ga": 0, "pts": 0})
            e = data.get(k)
            if not isinstance(e, dict):
                continue
            hs, as_ = e.get("homeScore"), e.get("awayScore")
            try:
                hs, as_ = int(hs), int(as_)
            except (TypeError, ValueError):
                continue
            stats[h]["p"] += 1; stats[a]["p"] += 1
            stats[h]["gf"] += hs; stats[h]["ga"] += as_
            stats[a]["gf"] += as_; stats[a]["ga"] += hs
            if hs > as_:   stats[h]["pts"] += 3
            elif as_ > hs: stats[a]["pts"] += 3
            else:          stats[h]["pts"] += 1; stats[a]["pts"] += 1
        table = sorted(stats.items(),
                       key=lambda kv: (-kv[1]["pts"], -(kv[1]["gf"] - kv[1]["ga"]),
                                       -kv[1]["gf"], kv[0]))
        complete = all(s["p"] == 3 for s in stats.values())
        res[gid] = ([norm_team(t) for t, _ in table], complete)
    return res


def match_winner(entry):
    """(winner, loser) as normalised names from a stored KO entry, or None."""
    if not isinstance(entry, dict):
        return None
    teams = (entry.get("_teams") or "").split(" vs ")
    if len(teams) != 2:
        return None
    try:
        hs, as_ = int(entry.get("homeScore")), int(entry.get("awayScore"))
    except (TypeError, ValueError):
        return None
    h, a = norm_team(teams[0]), norm_team(teams[1])
    if hs > as_: return h, a
    if as_ > hs: return a, h
    pm = re.match(r"\s*(\d+)\s*-\s*(\d+)", entry.get("penalties") or "")
    if pm:
        hp, ap = int(pm.group(1)), int(pm.group(2))
        if hp > ap: return h, a
        if ap > hp: return a, h
    return None


def resolve_ref(ref, data, standings):
    """Set of normalised team names a bracket ref could currently be, or None."""
    ref = ref.strip()
    m = re.match(r"^(1st|2nd|3rd|4th)\s+([A-L])$", ref)
    if m:
        table, complete = standings.get(m.group(2), ([], False))
        if not complete:
            return None
        pos = {"1st": 0, "2nd": 1, "3rd": 2, "4th": 3}[m.group(1)]
        return {table[pos]} if pos < len(table) else None
    m = re.match(r"^3rd\s+([A-L](?:/[A-L])+)$", ref)
    if m:
        out = set()
        for g in m.group(1).split("/"):
            table, complete = standings.get(g, ([], False))
            if complete and len(table) > 2:
                out.add(table[2])
        return out or None
    m = re.match(r"^(W|L)\s+(\S+)$", ref)
    if m:
        tag = m.group(2)
        key = tag if tag in KO_SLOTS else LABEL_TO_KEY.get(tag)
        wl = match_winner(data.get(key)) if key else None
        if not wl:
            return None
        return {wl[0] if m.group(1) == "W" else wl[1]}
    return {norm_team(ref)}


def ko_slot_for(x, y, data, standings):
    """Match a completed KO pairing (normalised names) onto an empty bracket
    slot. Returns (slot_key, reversed?) or (None, False)."""
    for key, (_label, href, aref) in KO_SLOTS.items():
        if key in data:
            continue
        hset = resolve_ref(href, data, standings)
        aset = resolve_ref(aref, data, standings)
        if not hset or not aset:
            continue
        if x in hset and y in aset:
            return key, False
        if y in hset and x in aset:
            return key, True
    return None, False


def remap_placeholders(data):
    """Migrate NEW# placeholder entries onto their real bracket slots, and
    canonicalise team spellings in _teams. Returns list of changed keys."""
    changed = []
    new_keys = sorted((k for k in data if re.match(r"^NEW\d+$", k)),
                      key=lambda k: int(k[3:]))
    for key in new_keys:
        e = data[key]
        teams = (e.get("_teams") or "").split(" vs ") if isinstance(e, dict) else []
        if len(teams) != 2:
            continue
        x, y = norm_team(teams[0]), norm_team(teams[1])
        slot, rev = ko_slot_for(x, y, data, compute_standings(data))
        if not slot:
            continue
        entry = data.pop(key)
        if rev:
            swap_home_away(entry)
            x, y = y, x
        entry["_teams"] = f"{CANON.get(x, teams[0].strip())} vs {CANON.get(y, teams[1].strip())}"
        data[slot] = entry
        changed.append(slot)
        print(f"  Remapped {key} → {slot} ({entry['_teams']})")
    # Canonicalise ESPN spellings in every _teams field (Congo DR → DR Congo …)
    for k, e in data.items():
        if not isinstance(e, dict) or not e.get("_teams"):
            continue
        parts = e["_teams"].split(" vs ")
        if len(parts) != 2:
            continue
        canon = " vs ".join(CANON.get(norm_team(p), p.strip()) for p in parts)
        if canon != e["_teams"]:
            e["_teams"] = canon
            if k not in changed:
                changed.append(k)
    return changed

# Fields to swap when ESPN's home/away is reversed vs the fixture order
_SWAP_PAIRS = [
    ("homeScore", "awayScore"), ("homeScorers", "awayScorers"),
    ("lineupH", "lineupA"), ("possH", "possA"), ("shotsH", "shotsA"),
    ("cornersH", "cornersA"), ("foulsH", "foulsA"),
]

def swap_home_away(entry):
    """Flip all home/away fields so the entry matches fixture (home, away) order."""
    for hk, ak in _SWAP_PAIRS:
        hv, av = entry.get(hk), entry.get(ak)
        if hv is not None or av is not None:
            entry[hk], entry[ak] = av, hv
    # Cards are prefixed "H: "/"A: " per line — swap those prefixes too
    for ck in ("yellows", "reds"):
        if entry.get(ck):
            entry[ck] = (entry[ck].replace("H:", "\x00").replace("A:", "H:").replace("\x00", "A:"))
    # Penalty shootout score is "h-a" — reverse it as well
    pm = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", entry.get("penalties") or "")
    if pm:
        entry["penalties"] = f"{pm.group(2)}-{pm.group(1)}"
    return entry

def fixture_key_for(home_name, away_name):
    """Return (key, reversed?) for an ESPN match, or (None, False) if unknown."""
    key = FIXTURE_LOOKUP.get(frozenset((norm_team(home_name), norm_team(away_name))))
    if not key:
        return None, False
    fh, _ = FIXTURE_SCHEDULE[key]
    return key, norm_team(home_name) != norm_team(fh)


def espn_get(url, retries=3, delay=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i < retries - 1:
                time.sleep(delay)
            else:
                raise


def extract_stats(data):
    """Pull possession/shots/corners/fouls from ESPN summary boxscore."""
    stats = {}
    teams = data.get("boxscore", {}).get("teams", [])
    if len(teams) < 2:
        return stats

    name_map = {"possessionPct": ("possH", "possA"),
                "totalShots":    ("shotsH", "shotsA"),
                "wonCorners":    ("cornersH", "cornersA"),
                "foulsCommitted":("foulsH", "foulsA")}

    home_stats = {s["name"]: s["displayValue"] for s in teams[0].get("statistics", [])}
    away_stats = {s["name"]: s["displayValue"] for s in teams[1].get("statistics", [])}

    for espn_key, (hk, ak) in name_map.items():
        if espn_key in home_stats:
            val = home_stats[espn_key]
            # Round possession to integer string
            try:
                val = str(round(float(val)))
            except ValueError:
                pass
            stats[hk] = val
        if espn_key in away_stats:
            val = away_stats[espn_key]
            try:
                val = str(round(float(val)))
            except ValueError:
                pass
            stats[ak] = val

    return stats


def build_lineup(roster_entry):
    """Build a newline-delimited lineup string from ESPN roster data."""
    starters = sorted(
        [p for p in roster_entry.get("roster", []) if p.get("starter")],
        key=lambda p: p.get("displayOrder", 99)
    )
    lines = []
    for p in starters:
        pos_abbr = p.get("position", {}).get("abbreviation", "")
        pos = POS_MAP.get(pos_abbr, pos_abbr)
        name = p.get("athlete", {}).get("displayName", "?")
        lines.append(f"{pos} {name}")
    return "\n".join(lines)


def _shorten(name):
    """'Michel Aebischer' -> 'M. Aebischer'; leave already-short names alone."""
    name = (name or "").strip()
    if not name or "." in name:
        return name
    parts = name.split()
    if len(parts) < 2:
        return name
    return parts[0][0] + ". " + " ".join(parts[1:])


def _short_name(p):
    a = p.get("athlete", {}) or {}
    return a.get("shortName") or _shorten(a.get("displayName") or "")


def sub_minutes(summary_data):
    """athleteId -> minute string for substitution key events (best-effort)."""
    out = {}
    for ev in summary_data.get("keyEvents", []) or []:
        t = ev.get("type") or {}
        tag = (str(t.get("id", "")) + str(t.get("text", ""))).lower()
        if "sub" not in tag:
            continue
        clock = (ev.get("clock") or {}).get("displayValue", "")
        for a in ev.get("athletesInvolved", []) or []:
            if a.get("id"):
                out[str(a["id"])] = clock
    return out


def build_formation_data(roster_entry, minute_map):
    """Return (formation, xi_string, subs_string) for one team roster.
    xi line:  'place;jersey;shortName;posAbbr'   (place 1..11, 1 = GK)
    posAbbr is ESPN's raw position tag (G, RB, CD-L, CM-R, CF-L, …) — kept raw
    so the pitch can place each player by role/side rather than by ESPN's
    (sometimes jumbled) formationPlace ordering.
    sub line: 'inJersey;inName;outJersey;outName;minute'
    """
    formation = roster_entry.get("formation") or ""
    starters = sorted(
        [p for p in roster_entry.get("roster", []) if p.get("starter")],
        key=lambda p: int(p.get("formationPlace") or 0)
    )
    xi = []
    for p in starters:
        pos = (p.get("position", {}) or {}).get("abbreviation", "")
        xi.append("%s;%s;%s;%s" % (
            p.get("formationPlace") or "", p.get("jersey") or "",
            _short_name(p), pos))
    subs = []
    for p in roster_entry.get("roster", []):
        if p.get("subbedIn") and p.get("subbedInFor"):
            outp = p.get("subbedInFor", {})
            outa = outp.get("athlete", {}) or {}
            outn = outa.get("shortName") or _shorten(outa.get("displayName") or "")
            aid = str(p.get("athlete", {}).get("id", ""))
            subs.append("%s;%s;%s;%s;%s" % (
                p.get("jersey") or "", _short_name(p),
                outp.get("jersey") or "", outn, minute_map.get(aid, "")))
    return formation, "\n".join(xi), "\n".join(subs)


def _event_player(ev):
    """Best-effort scorer/booked-player name for a key event."""
    parts = ev.get("participants") or []
    if parts:
        nm = (parts[0].get("athlete", {}) or {}).get("displayName", "")
        if nm:
            return nm
    txt = ev.get("shortText") or ev.get("text") or ""
    return re.sub(r"\s+(Own Goal.*|Goal.*|Penalty.*|.*Card.*)$", "", txt, flags=re.I).strip()


def extract_events(data, home_name, away_name):
    """Parse keyEvents for goals and cards. Returns (homeScorers, awayScorers, yellows, reds).

    Goals are identified by ESPN's ``scoringPlay`` flag (robust across the many
    goal subtypes like ``goal---header``/``penalty---scored``). For every goal
    ESPN's ``team`` field is already the *credited* team — including own goals —
    so no side-flipping is needed. Scorer/booked names come from
    ``participants`` with a shortText fallback.
    """
    home_goals, away_goals = [], []
    home_yellows, away_yellows = [], []
    home_reds, away_reds = [], []

    for ev in data.get("keyEvents", []):
        clock    = (ev.get("clock") or {}).get("displayValue", "")
        team     = (ev.get("team") or {}).get("displayName", "")
        ttext    = (ev.get("type", {}).get("text") or "").lower()
        ttype    = (ev.get("type", {}).get("type") or "").lower()
        is_home  = (team == home_name)
        player   = _event_player(ev)

        if ev.get("scoringPlay"):
            if "own" in ttext or "own" in ttype:
                suffix = " (OG)"
            elif "penalt" in ttext or "penalt" in ttype:
                suffix = " (pen)"
            else:
                suffix = ""
            entry = f"{player} {clock}{suffix}".strip()
            (home_goals if is_home else away_goals).append(entry)
        elif "red" in ttext or "red-card" in ttype:   # covers Red + Second-Yellow-Red
            (home_reds if is_home else away_reds).append(f"{player} {clock}".strip())
        elif "yellow" in ttext or "yellow-card" in ttype:
            (home_yellows if is_home else away_yellows).append(f"{player} {clock}".strip())

    def fmt_cards(home_list, away_list, prefix_h="H", prefix_a="A"):
        parts = []
        if home_list:
            parts.append(f"{prefix_h}: " + "\n{}: ".format(prefix_h).join(home_list))
        if away_list:
            parts.append(f"{prefix_a}: " + "\n{}: ".format(prefix_a).join(away_list))
        return "\n".join(parts)

    return (
        "\n".join(home_goals),
        "\n".join(away_goals),
        fmt_cards(home_yellows, away_yellows),
        fmt_cards(home_reds, away_reds),
    )


def extract_shootout(summary_data):
    """Return 'h-a' penalty shootout score from an ESPN summary, or None."""
    comps = summary_data.get("header", {}).get("competitions", [{}])
    c = comps[0] if comps else {}
    home = away = None
    for comp in c.get("competitors", []):
        sc = comp.get("shootoutScore")
        if sc is None:
            continue
        try:
            sc = int(float(sc))  # ESPN returns floats like 3.0
        except (TypeError, ValueError):
            continue
        if comp.get("homeAway") == "home":
            home = sc
        elif comp.get("homeAway") == "away":
            away = sc
    if home is not None and away is not None:
        return f"{home}-{away}"
    return None


def get_espn_summary(event_id):
    """Fetch and return ESPN summary data for a match."""
    time.sleep(1.5)  # polite rate limiting
    return espn_get(ESPN_SUMMARY.format(event_id))


def update_entry(entry, summary_data, home_name, away_name):
    """Merge ESPN data into an existing matchdata entry. Only fills missing fields."""
    changed = False

    # Stats
    if not all(k in entry for k in ["possH", "possA", "shotsH", "shotsA", "cornersH", "cornersA", "foulsH", "foulsA"]):
        stats = extract_stats(summary_data)
        for k, v in stats.items():
            if k not in entry:
                entry[k] = v
                changed = True

    # Lineups
    rosters = summary_data.get("rosters", [])
    if len(rosters) >= 2 and "lineupH" not in entry:
        entry["lineupH"] = build_lineup(rosters[0])
        changed = True
    if len(rosters) >= 2 and "lineupA" not in entry:
        entry["lineupA"] = build_lineup(rosters[1])
        changed = True

    # Formation, starting XI (jersey+place) and substitutions
    if len(rosters) >= 2:
        mm = sub_minutes(summary_data)
        fH, xiH, subH = build_formation_data(rosters[0], mm)
        fA, xiA, subA = build_formation_data(rosters[1], mm)
        for k, val in (("formH", fH), ("formA", fA), ("xiH", xiH), ("xiA", xiA)):
            if val and k not in entry:
                entry[k] = val; changed = True
        # subs accumulate during the match, so refresh if richer than stored
        for k, val in (("subsH", subH), ("subsA", subA)):
            if val and len(val) > len(entry.get(k, "")):
                entry[k] = val; changed = True

    # Scorers & cards — refresh whenever ESPN reports more events than we have
    # stored. Goals/cards accumulate during a match and the original source was
    # often incomplete, so we trust ESPN's richer list (counted by lines).
    hs, as_, yel, red = extract_events(summary_data, home_name, away_name)

    def _lines(s):
        return len([x for x in (s or "").split("\n") if x.strip()])

    for k, val in (("homeScorers", hs), ("awayScorers", as_),
                   ("yellows", yel), ("reds", red)):
        if val and _lines(val) > _lines(entry.get(k, "")):
            entry[k] = val; changed = True

    # Penalty shootout (knockout draws) — needed for bracket progression
    if not entry.get("penalties"):
        pens = extract_shootout(summary_data)
        if pens:
            entry["penalties"] = pens
            entry["status"] = "pen"
            changed = True

    return changed


def build_new_entry(summary_data, home_name, away_name, home_score, away_score):
    """Create a full matchdata entry from ESPN summary data."""
    entry = {
        "status": "ft",
        "homeScore": int(home_score),
        "awayScore": int(away_score),
        "homeScorers": "",
        "awayScorers": "",
    }
    hs, as_, yel, red = extract_events(summary_data, home_name, away_name)
    entry["homeScorers"] = hs
    entry["awayScorers"] = as_
    if yel: entry["yellows"] = yel
    if red: entry["reds"] = red

    pens = extract_shootout(summary_data)
    if pens:
        entry["penalties"] = pens
        entry["status"] = "pen"

    rosters = summary_data.get("rosters", [])
    if len(rosters) >= 1: entry["lineupH"] = build_lineup(rosters[0])
    if len(rosters) >= 2: entry["lineupA"] = build_lineup(rosters[1])

    if len(rosters) >= 2:
        mm = sub_minutes(summary_data)
        fH, xiH, subH = build_formation_data(rosters[0], mm)
        fA, xiA, subA = build_formation_data(rosters[1], mm)
        if fH: entry["formH"] = fH
        if fA: entry["formA"] = fA
        if xiH: entry["xiH"] = xiH
        if xiA: entry["xiA"] = xiA
        entry["subsH"] = subH
        entry["subsA"] = subA

    entry.update(extract_stats(summary_data))
    return entry


def discover_new_matches(data, known_event_ids):
    """
    Scan ESPN scoreboard for completed WC matches not yet covered by KNOWN_IDS.
    Returns list of {event_id, home_name, away_name, home_score, away_score}.
    """
    from datetime import datetime, timedelta
    new = []
    seen_ids = set(known_event_ids.values()) | {
        e["_espnId"] for e in data.values()
        if isinstance(e, dict) and "_espnId" in e
    }

    # Scan all WC2026 dates: group stage (Jun 11–27) + knockout stage (Jun 28–Jul 19)
    start = datetime(2026, 6, 11)
    end   = datetime(2026, 7, 19)
    d = start
    while d <= end:
        datestr = d.strftime("%Y%m%d")
        try:
            board = espn_get(ESPN_BOARD.format(datestr))
        except Exception as e:
            print(f"    Warning: couldn't fetch {datestr}: {e}")
            d += timedelta(days=1)
            continue

        for ev in board.get("events", []):
            eid = ev["id"]
            if eid in seen_ids:
                continue
            comps = ev.get("competitions", [{}])
            c = comps[0] if comps else {}
            if not c.get("status", {}).get("type", {}).get("completed"):
                continue
            competitors = c.get("competitors", [])
            home = next((x for x in competitors if x.get("homeAway") == "home"), {})
            away = next((x for x in competitors if x.get("homeAway") == "away"), {})
            new.append({
                "event_id":   eid,
                "home_name":  home.get("team", {}).get("displayName", ""),
                "away_name":  away.get("team", {}).get("displayName", ""),
                "home_score": home.get("score", "0"),
                "away_score": away.get("score", "0"),
            })
            seen_ids.add(eid)

        d += timedelta(days=1)
        time.sleep(0.5)

    return new


def next_available_key(data, group_letter):
    """Return next unused key like A3, A4, etc. for a group."""
    for n in range(1, 10):
        k = f"{group_letter}{n}"
        if k not in data:
            return k
    return None


def main():
    with open(MATCHDATA, encoding="utf-8") as f:
        data = json.load(f)

    updated_keys = []

    # --- Step 0: Repair placeholder keys / team spellings from earlier runs ---
    print("=== Remapping placeholders ===")
    updated_keys.extend(remap_placeholders(data))

    # --- Step 1: Update (or create) known matches ---
    # Worklist = hardcoded KNOWN_IDS plus every stored entry that already
    # carries an ESPN id (so discovered matches keep getting stats/lineups
    # filled in on later runs).
    worklist = dict(KNOWN_IDS)
    for k, e in data.items():
        if isinstance(e, dict) and e.get("_espnId") and k not in worklist:
            worklist[k] = e["_espnId"]

    print("\n=== Updating known matches ===")
    for key, event_id in worklist.items():
        print(f"  {key}: fetching ESPN event {event_id}...")
        try:
            summary   = get_espn_summary(event_id)
            rosters   = summary.get("rosters", [])
            home_name = rosters[0].get("team", {}).get("displayName", "") if rosters else ""
            away_name = rosters[1].get("team", {}).get("displayName", "") if len(rosters) > 1 else ""

            if key not in data:
                # Knockout match not yet in matchdata — create it if completed
                comps     = summary.get("header", {}).get("competitions", [{}])
                c         = comps[0] if comps else {}
                if not c.get("status", {}).get("type", {}).get("completed"):
                    print(f"       → not yet completed, skipping")
                    continue
                competitors = c.get("competitors", [])
                home_c = next((x for x in competitors if x.get("homeAway") == "home"), {})
                away_c = next((x for x in competitors if x.get("homeAway") == "away"), {})
                entry  = build_new_entry(summary, home_name, away_name,
                                         home_c.get("score", "0"), away_c.get("score", "0"))
                entry["_espnId"] = event_id
                entry["_teams"]  = f"{home_name} vs {away_name}"
                data[key] = entry
                updated_keys.append(key)
                print(f"       → created new entry ({home_name} vs {away_name})")
                continue

            entry = data[key]
            # Skip only when ALL data layers are present: stats + basic lineup + formation XI
            has_stats   = all(k in entry for k in ["possH","possA","shotsH","shotsA","cornersH","cornersA","foulsH","foulsA"])
            has_lineups = "lineupH" in entry and "lineupA" in entry
            has_xi      = "xiH" in entry and "xiA" in entry and entry.get("xiH") and entry.get("xiA")
            has_form    = "formH" in entry and "formA" in entry and entry.get("formH") and entry.get("formA")
            # Drawn KO matches need a shootout result to resolve the bracket
            needs_pens  = (key in KO_SLOTS and not entry.get("penalties")
                           and entry.get("homeScore") == entry.get("awayScore")
                           and entry.get("homeScore") is not None)
            if has_stats and has_lineups and has_xi and has_form and not needs_pens:
                print(f"       → complete, skipping")
                continue

            if "_espnId" not in entry:
                entry["_espnId"] = event_id
                updated_keys.append(key)
            if update_entry(entry, summary, home_name, away_name):
                if key not in updated_keys:
                    updated_keys.append(key)
                print(f"       → updated")
            else:
                print(f"       → nothing new")
        except Exception as e:
            print(f"       → error: {e}")

    # --- Step 2: Discover and add brand-new matches ---
    print("\n=== Scanning for new matches ===")
    try:
        new_matches = discover_new_matches(data, KNOWN_IDS)
        print(f"Found {len(new_matches)} completed matches not yet in matchdata.json")
        for m in new_matches:
            print(f"  New match: {m['home_name']} {m['home_score']}-{m['away_score']} {m['away_name']} (ESPN {m['event_id']})")
            # Map onto the real fixture key (A3, C4, …) by team names.
            assigned_key, reversed_order = fixture_key_for(m["home_name"], m["away_name"])

            if assigned_key and assigned_key in data:
                # Fixture already has data — don't clobber manual edits.
                print(f"  → {assigned_key} already populated, skipping")
                continue

            if not assigned_key:
                # Knockout match — resolve the bracket slot from standings
                # and previous round results.
                assigned_key, reversed_order = ko_slot_for(
                    norm_team(m["home_name"]), norm_team(m["away_name"]),
                    data, compute_standings(data))
                if assigned_key:
                    print(f"  → assigning knockout slot {assigned_key}"
                          + (" (home/away reversed vs bracket — swapping)" if reversed_order else ""))

            if not assigned_key:
                # Truly unknown fixture — fall back to a placeholder NEW# key
                # (remap_placeholders will move it once the bracket resolves).
                reversed_order = False
                for n in range(1, 99):
                    candidate = f"NEW{n}"
                    if candidate not in data:
                        assigned_key = candidate
                        break
                print(f"  → no fixture match; assigning placeholder {assigned_key}")
            elif assigned_key in FIXTURE_SCHEDULE:
                print(f"  → assigning fixture key {assigned_key}"
                      + (" (home/away reversed vs fixture — swapping)" if reversed_order else ""))

            try:
                summary = get_espn_summary(m["event_id"])
                rosters = summary.get("rosters", [])
                home_name = rosters[0].get("team", {}).get("displayName", m["home_name"]) if rosters else m["home_name"]
                away_name = rosters[1].get("team", {}).get("displayName", m["away_name"]) if len(rosters) > 1 else m["away_name"]
                entry = build_new_entry(summary, home_name, away_name, m["home_score"], m["away_score"])
                if reversed_order:
                    swap_home_away(entry)
                # Store ESPN ID so future runs dedupe against it.
                entry["_espnId"] = m["event_id"]
                if assigned_key in FIXTURE_SCHEDULE:
                    fh = FIXTURE_SCHEDULE[assigned_key]
                    entry["_teams"] = f"{fh[0]} vs {fh[1]}"
                else:
                    # Slot orientation + canonical tracker spellings
                    hn, an = (away_name, home_name) if reversed_order else (home_name, away_name)
                    entry["_teams"] = (f"{CANON.get(norm_team(hn), hn)} vs "
                                       f"{CANON.get(norm_team(an), an)}")
                data[assigned_key] = entry
                updated_keys.append(assigned_key)
                print(f"     → added as {assigned_key}")
            except Exception as e:
                print(f"     → error: {e}")
    except Exception as e:
        print(f"  Error during discovery: {e}")

    # --- Save ---
    if updated_keys:
        with open(MATCHDATA, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n✓ Saved updates for: {', '.join(updated_keys)}")
    else:
        print("\nNo updates needed.")


if __name__ == "__main__":
    main()
