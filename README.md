# WEC Strategy

Análisis del ritmo por vuelta en carreras de resistencia (WEC, LMP2, LMGT3).

```
wec-strategy/
├── backend/                  Python: importar, analizar y servir los datos
│   ├── src/                  importer, laps, metrics, api, main, config
│   ├── tests/                pruebas
│   ├── parked/               stints, boxes y degradación (aparcados)
│   ├── data/raw/WEC/2026/Barcelona/   CSV/Excel originales
│   └── requirements.txt
└── frontend/                 React + TypeScript + Vite
    ├── src/                  App.tsx, api.ts, index.css, main.tsx
    └── package.json
```

El frontend solo habla con el backend por HTTP: cada carpeta se puede
ejecutar, probar y desplegar por separado.

## Arranque (dos terminales)

```bash
# 1) Backend  ->  http://localhost:8000  (docs en /docs)
cd backend
pip install -r requirements.txt
cd src && uvicorn api:app --reload --port 8000

# 2) Frontend  ->  http://localhost:5173
cd frontend
npm install
npm run dev
```

- Coloca los CSV/Excel en `backend/data/raw/WEC/2026/Barcelona/`
  (u otra carpeta: `WEC_DATA_DIR=/ruta uvicorn api:app --port 8000`).
- URL del backend distinta: copia `frontend/.env.example` a `frontend/.env`.
- Pruebas del backend: `cd backend && python -m pytest tests`
- Comprobación de tipos del frontend: `cd frontend && npm run check`
- Informe por consola sin interfaz: `python backend/src/main.py archivo.CSV --car 007`

## Endpoints

| Ruta | Devuelve |
|---|---|
| `GET /api/sessions` | sesiones disponibles y ajustes (separador de milésimas, umbral) |
| `GET /api/sessions/{sesión}/overview` | resumen de la sesión y de cada categoría |
| `GET /api/sessions/{sesión}/categories/{cat}?slow=107` | mejores tiempos, clasificaciones (vuelta, S1, S2, S3), 4 coches más rápidos, lista de coches |
| `GET /api/sessions/{sesión}/cars/{número}?slow=107` | KPIs por piloto y todas las vueltas del coche con su estado |
