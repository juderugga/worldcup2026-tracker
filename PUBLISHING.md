# Publishing the World Cup 2026 Tracker to GitHub Pages

The public page is a single self-contained file — `docs/index.html` — with all match
data embedded. Visitors just see the stats: Today, Groups, Path to Final, Stats & Scorers.
No server, no editing, no backup buttons.

## One-time setup

1. Create a **public** repo on GitHub (e.g. `worldcup2026-tracker`).
2. From this folder:

   ```bash
   git init
   git add worldcup2026.html matchdata.json update_matches.py update_matches_chunked.py \
           server.py publish.py start.sh docs/ PUBLISHING.md
   git commit -m "World Cup 2026 tracker"
   git branch -M main
   git remote add origin https://github.com/<your-username>/worldcup2026-tracker.git
   git push -u origin main
   ```

3. On GitHub: **Settings → Pages → Build and deployment**
   - Source: *Deploy from a branch*
   - Branch: `main`, folder: `/docs`
   - Save.

Your page goes live at `https://<your-username>.github.io/worldcup2026-tracker/`
(first deploy takes a minute or two).

## Updating scores after each matchday

```bash
python3 update_matches.py      # pull latest results from ESPN
python3 publish.py             # rebuild docs/index.html with fresh data
git add matchdata.json docs/
git commit -m "Results through <date>"
git push
```

GitHub Pages redeploys automatically on push — the public page updates within a minute.

## Notes

- `docs/.nojekyll` is created by `publish.py` so Pages serves the file as-is.
- Only commit what you want public. The private tracker (`worldcup2026.html` +
  `server.py`) still works locally exactly as before — `./start.sh`.
- If you'd rather keep the source private, create the repo with **only** the
  `docs/` folder and this file.
