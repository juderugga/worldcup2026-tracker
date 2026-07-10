#!/usr/bin/env python3
"""
publish.py — build the public, read-only GitHub Pages version of the tracker.

Takes worldcup2026.html + matchdata.json and produces docs/index.html:
  * match data is EMBEDDED into the page (no server needed)
  * everything marked <!-- LOCAL-ONLY --> ... <!-- /LOCAL-ONLY --> is removed
    (edit buttons, backup/restore, My Team & Predictions tabs, update bar)
  * score editing in the match modal is hidden

Usage:  python3 publish.py        then commit & push the docs/ folder.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_HTML = os.path.join(HERE, "worldcup2026.html")
SRC_DATA = os.path.join(HERE, "matchdata.json")
OUT_DIR = os.path.join(HERE, "docs")
OUT_HTML = os.path.join(OUT_DIR, "index.html")

READONLY_CSS = """
/* ── public read-only build ── */
.modal-edit-toggle, .modal-save-btn, .auto-fetch-note, #match-edit { display: none !important; }
"""

FOOTER = """
<footer style="text-align:center;padding:18px 10px 26px;font-size:11px;color:var(--text3)">
  FIFA World Cup 2026™ unofficial results tracker · Updated after every matchday ·
  Built with ❤ — data shown is embedded at publish time
</footer>
"""


def main():
    html = open(SRC_HTML, encoding="utf-8").read()
    data = json.load(open(SRC_DATA, encoding="utf-8"))

    # 1) strip everything local-only
    html, n = re.subn(r"<!-- LOCAL-ONLY -->.*?<!-- /LOCAL-ONLY -->", "", html, flags=re.S)
    print(f"  removed {n} LOCAL-ONLY block(s)")

    # 2) embed the match data before the main script
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    # NB: plain str.replace — regex replacement would mangle \n escapes in the JSON
    embed = f"<script>window.EMBEDDED_DATA = {payload};</script>\n<script>"
    if "<script>" not in html:
        sys.exit("ERROR: could not find <script> tag to embed data")
    html = html.replace("<script>", embed, 1)
    played = sum(1 for k, v in data.items()
                 if not k.startswith("_") and isinstance(v, dict)
                 and v.get("status") and v.get("status") != "ns")
    print(f"  embedded {played} played matches")

    # 3) hide modal editing
    html = html.replace("</style>", READONLY_CSS + "</style>", 1)

    # 4) footer
    html = html.replace("</body>", FOOTER + "</body>", 1)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    # .nojekyll stops GitHub Pages from running Jekyll (faster deploys)
    open(os.path.join(OUT_DIR, ".nojekyll"), "w").close()
    print(f"  wrote {os.path.relpath(OUT_HTML, HERE)} ({len(html)//1024} KB)")
    print("Done. Commit the docs/ folder and push to publish.")


if __name__ == "__main__":
    main()
