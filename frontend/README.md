# VOULT frontend

React 19 + Vite 6 + TailwindCSS 3.4. Pixel/terminal aesthetic (Silkscreen
display, JetBrains Mono body), CRT scanlines + grain. Three routes: landing,
`/launch` (the launcher wizard), `/verify` (check a coin).

## Run locally

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /api -> http://localhost:8000
```

Run the backend (`../backend`) on port 8000 at the same time.

## Build & deploy (Netlify, drag-and-drop)

```bash
npm run build    # outputs dist/
```

Drag the `dist/` folder into Netlify. The included `public/_redirects` does two
things in production:

1. Proxies `/api/*` to your backend — **edit the Render URL** in
   `public/_redirects` to point at your deployed backend.
2. SPA fallback so client-side routes resolve to `index.html`.

## Structure

```
src/
  api.js                 fetch wrapper, token in sessionStorage
  App.jsx                router + login modal
  components/
    Nav.jsx              top bar
    LoginModal.jsx       wallet + password session
    ui.jsx               Button / Panel / Label / Tag primitives
  pages/
    Landing.jsx          hero, 4-step process, asset grid, pipeline
    Launch.jsx           config -> create -> fund -> start -> live progress
    Verify.jsx           mint lookup against /api/verify
```

The asset picker loads from `GET /api/assets` and falls back to a static list
if the backend is unreachable.
