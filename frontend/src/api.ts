import { useEffect, useState } from "react"

// URL del backend. Para cambiarla: VITE_API_URL=http://otro-host:8000 en un .env
const BASE = (import.meta.env?.VITE_API_URL as string | undefined) ?? "http://localhost:8000"

// ---------------------------------------------------------------------------
// Tipos (reflejan exactamente las respuestas de src/api.py)
// ---------------------------------------------------------------------------
export type Metric = "lap" | "s1" | "s2" | "s3"

export type TimeValue = { seconds: number | null; text: string }

export type Settings = { msSeparator: string; slowThresholdPct: number }
export type SessionInfo = { id: string; name: string }
export type SessionsResponse = {
  sessions: SessionInfo[]
  settings: Settings
  dataDir: string
}

export type Best = TimeValue & {
  key: Metric
  label: string
  car: string
  team: string
  driver: string
  lap: number
  clock: string
  elapsed: string
}

export type CategorySummary = {
  id: string
  label: string
  cars: number
  drivers: number
  laps: number
  bestLap: Best
}
export type Overview = {
  session: SessionInfo
  notices: string[]
  laps: number
  cars: number
  drivers: number
  clockStart: string
  clockEnd: string
  categories: CategorySummary[]
}

export type RankingRow = TimeValue & {
  position: number
  car: string
  team: string
  driver: string
  gapText: string
  lap: number
  clock: string
}
export type CarPace = {
  car: string
  team: string
  laps: { lap: number; seconds: number | null; driver: string }[]
}
export type CarOption = {
  number: string
  team: string
  manufacturer: string
  drivers: string[]
}
export type CategoryData = {
  category: { id: string; label: string }
  counts: { laps: number; paceLaps: number; cars: number; drivers: number }
  bests: Best[]
  rankings: Record<Metric, RankingRow[]>
  pace: CarPace[]
  cars: CarOption[]
}

export type DriverRow = {
  name: string
  laps: number
  paceLaps: number
  best: TimeValue
  s1: TimeValue
  s2: TimeValue
  s3: TimeValue
  median: TimeValue
  medianGap: TimeValue
  deltaText: string
}
export type CarLap = TimeValue & {
  lap: number
  stint: number
  stintLap: number
  driver: string
  s1: string
  s2: string
  s3: string
  clock: string
  status: string
  isPace: boolean
}
export type StintRow = {
  stint: number
  driver: string
  startLap: number
  endLap: number
  laps: number
  paceLaps: number
  best: TimeValue
  median: TimeValue
  // tiempo ≈ intercept + slope × (vuelta del stint); null si hay pocas vueltas de ritmo
  trend: { slope: number; intercept: number; r2: number | null } | null
}
export type CarData = {
  car: { number: string; team: string; manufacturer: string; category: string }
  counts: { laps: number; paceLaps: number }
  drivers: DriverRow[]
  stints: StintRow[]
  laps: CarLap[]
}

// ---------------------------------------------------------------------------
// Formato de tiempos (mismo criterio que format_lap_time de Python).
// El separador de milésimas lo manda el backend (config.MS_SEPARATOR).
// ---------------------------------------------------------------------------
let msSeparator = "."

export function setMsSeparator(separator: string) {
  msSeparator = separator
}

export function formatLapTime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "–"
  const totalMs = Math.round(seconds * 1000)
  const minutes = Math.floor(totalMs / 60000)
  const rest = ((totalMs % 60000) / 1000).toFixed(3).padStart(6, "0")
  return `${String(minutes).padStart(2, "0")}:${rest.replace(".", msSeparator)}`
}

export function formatSeconds(seconds: number): string {
  return seconds.toFixed(3).replace(".", msSeparator)
}

export function formatSigned(seconds: number): string {
  const sign = seconds >= 0 ? "+" : "-"
  return `${sign}${Math.abs(seconds).toFixed(3).replace(".", msSeparator)}`
}

export function timeFormatLabel(): string {
  return `mm:ss${msSeparator}ddd`
}

// ---------------------------------------------------------------------------
// Llamadas
// ---------------------------------------------------------------------------
async function get<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`)
  } catch {
    throw new Error(
      `No se pudo conectar con el backend (${BASE}). ¿Está arrancado? Desde la carpeta src: uvicorn api:app --port 8000`,
    )
  }
  if (!response.ok) {
    let detail = `Error ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      // la respuesta no traía JSON: se deja el código de estado
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

const enc = encodeURIComponent

export const api = {
  sessions: () => get<SessionsResponse>("/api/sessions"),
  overview: (session: string) =>
    get<Overview>(`/api/sessions/${enc(session)}/overview`),
  category: (session: string, category: string, slow: number) =>
    get<CategoryData>(
      `/api/sessions/${enc(session)}/categories/${enc(category)}?slow=${slow}`,
    ),
  car: (session: string, number: string, slow: number) =>
    get<CarData>(`/api/sessions/${enc(session)}/cars/${enc(number)}?slow=${slow}`),
}

// ---------------------------------------------------------------------------
// Hook: carga de datos con estado. `load = null` significa "todavía no".
// Al cambiar las dependencias se vacía el dato y se vuelve a pedir.
// ---------------------------------------------------------------------------
type State<T> = { data: T | null; error: string | null; loading: boolean }

export function useApi<T>(load: (() => Promise<T>) | null, deps: unknown[]): State<T> {
  const [state, setState] = useState<State<T>>({
    data: null,
    error: null,
    loading: load !== null,
  })

  useEffect(() => {
    if (!load) {
      setState({ data: null, error: null, loading: false })
      return
    }
    let cancelled = false
    setState({ data: null, error: null, loading: true })
    load()
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false })
      })
      .catch((error: Error) => {
        if (!cancelled) setState({ data: null, error: error.message, loading: false })
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return state
}