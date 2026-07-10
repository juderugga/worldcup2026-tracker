#!/usr/bin/env python3
"""Chunked runner for update_matches.py — does the same work as main(),
but checkpoints progress so it can resume across short executions.
Prints CONTINUE if more work remains, DONE when finished."""
import json, os, sys, time as _time
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CKPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wc_update_checkpoint.json")
BUDGET = 27.0  # seconds of work per invocation
START = _time.monotonic()

sys.path.insert(0, SCRIPT_DIR)
# Cap polite-rate-limit sleeps to keep chunks small
_real_sleep = _time.sleep
_time.sleep = lambda s: _real_sleep(min(s, 0.3))

import update_matches as um

def out_of_time():
    return _time.monotonic() - START > BUDGET

def load_ckpt():
    if os.path.exists(CKPT):
        with open(CKPT) as f:
            return json.load(f)
    return {"phase": 0, "done_keys": [], "scan_date": "2026-06-11",
            "pending": [], "updated_keys": [], "log": []}

def save(data, ck, changed):
    if changed:
        with open(um.MATCHDATA, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    with open(CKPT, "w") as f:
        json.dump(ck, f)

def note(ck, msg):
    print(msg)
    ck["log"].append(msg)

def main():
    with open(um.MATCHDATA, encoding="utf-8") as f:
        data = json.load(f)
    ck = load_ckpt()
    changed = False

    # Phase 0: remap placeholders (no network)
    if ck["phase"] == 0:
        ch = um.remap_placeholders(data)
        if ch:
            ck["updated_keys"].extend(ch)
            note(ck, f"Remapped/canonicalised: {', '.join(ch)}")
            changed = True
        ck["phase"] = 1

    # Phase 1: known matches worklist
    if ck["phase"] == 1:
        worklist = dict(um.KNOWN_IDS)
        for k, e in data.items():
            if isinstance(e, dict) and e.get("_espnId") and k not in worklist:
                worklist[k] = e["_espnId"]
        for key, event_id in worklist.items():
            if key in ck["done_keys"]:
                continue
            if out_of_time():
                save(data, ck, changed); print("CONTINUE"); return
            try:
                summary = um.get_espn_summary(event_id)
                rosters = summary.get("rosters", [])
                home_name = rosters[0].get("team", {}).get("displayName", "") if rosters else ""
                away_name = rosters[1].get("team", {}).get("displayName", "") if len(rosters) > 1 else ""
                if key not in data:
                    comps = summary.get("header", {}).get("competitions", [{}])
                    c = comps[0] if comps else {}
                    if not c.get("status", {}).get("type", {}).get("completed"):
                        ck["done_keys"].append(key)
                        continue
                    competitors = c.get("competitors", [])
                    hc = next((x for x in competitors if x.get("homeAway") == "home"), {})
                    ac = next((x for x in competitors if x.get("homeAway") == "away"), {})
                    entry = um.build_new_entry(summary, home_name, away_name,
                                               hc.get("score", "0"), ac.get("score", "0"))
                    entry["_espnId"] = event_id
                    entry["_teams"] = f"{home_name} vs {away_name}"
                    data[key] = entry
                    ck["updated_keys"].append(key)
                    note(ck, f"{key}: created new entry ({home_name} vs {away_name})")
                    changed = True
                    ck["done_keys"].append(key)
                    continue
                entry = data[key]
                has_stats = all(k in entry for k in ["possH","possA","shotsH","shotsA","cornersH","cornersA","foulsH","foulsA"])
                has_lineups = "lineupH" in entry and "lineupA" in entry
                has_xi = entry.get("xiH") and entry.get("xiA")
                has_form = entry.get("formH") and entry.get("formA")
                needs_pens = (key in um.KO_SLOTS and not entry.get("penalties")
                              and entry.get("homeScore") == entry.get("awayScore")
                              and entry.get("homeScore") is not None)
                if has_stats and has_lineups and has_xi and has_form and not needs_pens:
                    ck["done_keys"].append(key)
                    continue
                if "_espnId" not in entry:
                    entry["_espnId"] = event_id
                    if key not in ck["updated_keys"]:
                        ck["updated_keys"].append(key)
                    changed = True
                if um.update_entry(entry, summary, home_name, away_name):
                    if key not in ck["updated_keys"]:
                        ck["updated_keys"].append(key)
                    note(ck, f"{key}: updated")
                    changed = True
            except Exception as e:
                note(ck, f"{key}: error: {e}")
            ck["done_keys"].append(key)
        ck["phase"] = 2

    # Phase 2: discovery scan (chunked by date, only up to today)
    if ck["phase"] == 2:
        seen = set(um.KNOWN_IDS.values()) | {
            e["_espnId"] for e in data.values()
            if isinstance(e, dict) and "_espnId" in e}
        seen |= {m["event_id"] for m in ck["pending"]}
        end = min(datetime(2026, 7, 19), datetime.now())
        d = datetime.strptime(ck["scan_date"], "%Y-%m-%d")
        while d <= end:
            if out_of_time():
                save(data, ck, changed); print("CONTINUE"); return
            try:
                board = um.espn_get(um.ESPN_BOARD.format(d.strftime("%Y%m%d")))
                for ev in board.get("events", []):
                    eid = ev["id"]
                    if eid in seen:
                        continue
                    comps = ev.get("competitions", [{}])
                    c = comps[0] if comps else {}
                    if not c.get("status", {}).get("type", {}).get("completed"):
                        continue
                    cs = c.get("competitors", [])
                    h = next((x for x in cs if x.get("homeAway") == "home"), {})
                    a = next((x for x in cs if x.get("homeAway") == "away"), {})
                    ck["pending"].append({
                        "event_id": eid,
                        "home_name": h.get("team", {}).get("displayName", ""),
                        "away_name": a.get("team", {}).get("displayName", ""),
                        "home_score": h.get("score", "0"),
                        "away_score": a.get("score", "0")})
                    seen.add(eid)
            except Exception as e:
                note(ck, f"Warning: couldn't scan {d.date()}: {e}")
            d += timedelta(days=1)
            ck["scan_date"] = d.strftime("%Y-%m-%d")
        ck["phase"] = 3
        if ck["pending"]:
            note(ck, f"Discovery: {len(ck['pending'])} completed matches not yet in matchdata.json")

    # Phase 3: add discovered matches
    if ck["phase"] == 3:
        while ck["pending"]:
            if out_of_time():
                save(data, ck, changed); print("CONTINUE"); return
            m = ck["pending"][0]
            assigned_key, rev = um.fixture_key_for(m["home_name"], m["away_name"])
            if assigned_key and assigned_key in data:
                note(ck, f"{m['home_name']} vs {m['away_name']}: {assigned_key} already populated, skipping")
                ck["pending"].pop(0)
                continue
            if not assigned_key:
                assigned_key, rev = um.ko_slot_for(
                    um.norm_team(m["home_name"]), um.norm_team(m["away_name"]),
                    data, um.compute_standings(data))
            if not assigned_key:
                rev = False
                for n in range(1, 99):
                    if f"NEW{n}" not in data:
                        assigned_key = f"NEW{n}"
                        break
            try:
                summary = um.get_espn_summary(m["event_id"])
                rosters = summary.get("rosters", [])
                hn = rosters[0].get("team", {}).get("displayName", m["home_name"]) if rosters else m["home_name"]
                an = rosters[1].get("team", {}).get("displayName", m["away_name"]) if len(rosters) > 1 else m["away_name"]
                entry = um.build_new_entry(summary, hn, an, m["home_score"], m["away_score"])
                if rev:
                    um.swap_home_away(entry)
                entry["_espnId"] = m["event_id"]
                if assigned_key in um.FIXTURE_SCHEDULE:
                    fh = um.FIXTURE_SCHEDULE[assigned_key]
                    entry["_teams"] = f"{fh[0]} vs {fh[1]}"
                else:
                    h2, a2 = (an, hn) if rev else (hn, an)
                    entry["_teams"] = (f"{um.CANON.get(um.norm_team(h2), h2)} vs "
                                       f"{um.CANON.get(um.norm_team(a2), a2)}")
                data[assigned_key] = entry
                ck["updated_keys"].append(assigned_key)
                note(ck, f"Added {m['home_name']} {m['home_score']}-{m['away_score']} {m['away_name']} as {assigned_key}")
                changed = True
            except Exception as e:
                note(ck, f"Error adding {m['home_name']} vs {m['away_name']}: {e}")
            ck["pending"].pop(0)
        ck["phase"] = 4

    save(data, ck, changed)
    os.path.exists(CKPT) and os.remove(CKPT); print("DONE")
    print("UPDATED_KEYS:", ", ".join(ck["updated_keys"]) if ck["updated_keys"] else "(none)")

main()
