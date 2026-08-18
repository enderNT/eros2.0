# panel-ui

El panel de control (`/admin`). Vite + React + TypeScript; se compila dentro de
`src/agente/web/static/panel`, que es lo que sirve FastAPI. No es un deploy aparte.

```bash
npm install
npm run build          # produce el bundle que sirve /admin
npm run dev            # dev server con proxy a uvicorn en :8000
```

`npm run dev` asume que el backend ya corre (`uvicorn agente.app:app --port 8000`);
proxya `/admin/api` hacia él, así que la cookie de sesión es del mismo origen y no
hay CORS ni en desarrollo.

Todo lo que el panel lee o escribe pasa por `/admin/api` (`src/agente/web/panel_api.py`).
