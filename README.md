# NESAT 2000

NESAT 2000 is a small Python search engine that crawls pages itself, stores an index in SQLite, and serves a retro 98.css-style web interface.

## What it does

- Crawls HTML pages using Python's standard library
- Respects `robots.txt` when available
- Extracts page titles, text, and links
- Stores pages and term frequencies in `data/index.db`
- Searches only the pages it indexed itself
- Uses the 98.css framework plus local icon files from `imageres/`
- Automatically builds a default 100+ page index from built-in source sites

## Run it

```powershell
python app.py
```

Then open `http://127.0.0.1:8020/index.html`.

## Deploy on Render

This project is now Render-ready:

- `app.py` reads Render's `PORT` automatically
- `requirements.txt` is included
- `.python-version` pins Python `3.11`
- `render.yaml` is included for a basic web service named `nesa98`

If this folder is the root of your GitHub repo, you can connect the repo in Render and create a Python Web Service.
Render settings:

- Build Command: `pip install -r requirements.txt`
- Start Command: `python app.py`

Render will provide the public URL after the first successful deploy.

## No terminal

Double-click `launch.pyw` or `Start NESAT 2000.vbs` to start NESAT 2000 without a terminal window. It opens the browser automatically.
If Windows blocks those, use `Start NESAT 2000.bat`.

## Search flow

- Wait for the automatic web index to build.
- Then type a search and press Enter.
- The search bar now has `Find:` and `Clear:` buttons.
- The bottom of the page shows live BBC top stories when the feed is reachable.

## Notes

- If you open `index.html` directly from disk, it redirects to the local server.
- The 98.css base stylesheet is loaded from its CDN. The custom retro layout lives in `static/style.css`.
