import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react"
import {
  api,
  formatLapTime,
  formatSeconds,
  formatSigned,
  setMsSeparator,
  timeFormatLabel,
  useApi,
  type CarData,
  type CategoryData,
  type Metric,
  type Overview,
  type RankingRow,
  type SessionInfo,
} from "./api"

// ---------------------------------------------------------------------------
// Textos e imágenes estáticos (lo demás viene del backend)
// ---------------------------------------------------------------------------
const photos: Record<string, string> = {
  hypercar:
    "https://images.unsplash.com/photo-1784654682177-e312b0ed52fa?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1400",
  lmgt3:
    "https://images.unsplash.com/photo-1786640779712-8b9a6d93ec1b?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=85&w=1400",
}

const categoryCopy: Record<string, { description: string; badge: string }> = {
  HYPERCAR: {
    description:
      "Compara prototipos, detecta la tendencia y encuentra el ritmo más competitivo.",
    badge: "HYP / PROTOTIPOS",
  },
  LMGT3: {
    description:
      "Evalúa la consistencia de los GT y compara el rendimiento de los pilotos en un mismo coche.",
    badge: "GT3 / GRAN TURISMO",
  },
}
const fallbackCopy = {
  description: "Analiza el ritmo de cada coche y la diferencia entre sus pilotos.",
  badge: "WEC",
}

const METRIC_TABS: { key: Metric; label: string; title: string }[] = [
  { key: "lap", label: "Resumen de ritmo", title: "Mejor vuelta" },
  { key: "s1", label: "Sector 1", title: "Mejor sector 1" },
  { key: "s2", label: "Sector 2", title: "Mejor sector 2" },
  { key: "s3", label: "Sector 3", title: "Mejor sector 3" },
]

const SLOW_OPTIONS = [105, 107, 110, 115, 120]

// Color + forma: la forma identifica la serie aunque no se distingan los colores.
const PALETTE = ["#2F80FF", "#42D6FF", "#9D86FF", "#7B91AD", "#FFB454", "#5BD19F"]
type Shape = "circle" | "diamond" | "square" | "triangle" | "cross"
const SHAPES: Shape[] = ["circle", "diamond", "square", "triangle", "circle", "diamond"]
const DRIVER_PALETTE = ["#D4F25C", "#5FD3E8", "#B79CFF", "#FFB454", "#5BD19F", "#FF8FA3"]
const EXCLUDED_COLOR = "#8392A5"

type Mode = "ritmo" | "todas"

// ---------------------------------------------------------------------------
// Iconos y marca
// ---------------------------------------------------------------------------
function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  }
  if (name === "chart")
    return (
      <svg {...common}>
        <path d="M4 19V9m6 10V5m6 14v-7m4 7H2" />
      </svg>
    )
  if (name === "grid")
    return (
      <svg {...common}>
        <rect x="4" y="4" width="6" height="6" rx="1" />
        <rect x="14" y="4" width="6" height="6" rx="1" />
        <rect x="4" y="14" width="6" height="6" rx="1" />
        <rect x="14" y="14" width="6" height="6" rx="1" />
      </svg>
    )
  if (name === "download")
    return (
      <svg {...common}>
        <path d="M12 3v12m-4-4 4 4 4-4M5 20h14" />
      </svg>
    )
  if (name === "chevron")
    return (
      <svg {...common}>
        <path d="m9 18 6-6-6-6" />
      </svg>
    )
  if (name === "flag")
    return (
      <svg {...common}>
        <path d="M5 21V4m0 1c5-3 8 3 14 0v9c-6 3-9-3-14 0" />
      </svg>
    )
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l3 2" />
    </svg>
  )
}

function Logo({ onClick }: { onClick?: () => void }) {
  return (
    <button className="logo" onClick={onClick} aria-label="Volver al inicio">
      <span className="mark">
        <i />
        <i />
        <i />
      </span>
      <span>RACE STRATEGY</span>
      <small>BY BG</small>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Gráfica de líneas con tooltip al pasar el ratón
// ---------------------------------------------------------------------------
type Point = { x: number; y: number; who: string; note?: string; best?: boolean }
type Series = {
  id: string
  label: string
  color: string
  shape: Shape
  line: boolean
  dashed?: boolean // línea discontinua que une todos sus puntos (tendencia)
  dash?: string // patrón de trazo (stroke-dasharray) para distinguir series del mismo color
  markers?: boolean // false: solo línea, sin puntos
  points: Point[]
}
// Franja de fondo con una etiqueta (p. ej. un stint) entre dos vueltas.
type Band = { from: number; to: number; label: string; short: string }

function Marker({
  shape,
  x,
  y,
  r,
  color,
}: {
  shape: Shape
  x: number
  y: number
  r: number
  color: string
}) {
  const common = { fill: color, stroke: "#0d1621", strokeWidth: 1 }
  if (shape === "diamond")
    return (
      <polygon
        {...common}
        points={`${x},${y - r * 1.3} ${x + r * 1.3},${y} ${x},${y + r * 1.3} ${x - r * 1.3},${y}`}
      />
    )
  if (shape === "square")
    return <rect {...common} x={x - r} y={y - r} width={r * 2} height={r * 2} />
  if (shape === "triangle")
    return (
      <polygon
        {...common}
        points={`${x},${y - r * 1.3} ${x + r * 1.25},${y + r} ${x - r * 1.25},${y + r}`}
      />
    )
  if (shape === "cross")
    return (
      <g stroke={color} strokeWidth={2} strokeLinecap="round">
        <line x1={x - r} y1={y - r} x2={x + r} y2={y + r} />
        <line x1={x - r} y1={y + r} x2={x + r} y2={y - r} />
      </g>
    )
  return <circle {...common} cx={x} cy={y} r={r} />
}

function Legend({ series }: { series: Series[] }) {
  return (
    <div className="legend">
      {series.map((s) => (
        <span key={s.id}>
          <svg width="24" height="12" viewBox="0 0 24 12" aria-hidden="true">
            {s.line && (
              <line
                x1="1"
                y1="6"
                x2="23"
                y2="6"
                stroke={s.color}
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray={s.dash ?? (s.dashed ? "6 4" : undefined)}
              />
            )}
            <Marker shape={s.shape} x={12} y={6} r={3.4} color={s.color} />
          </svg>
          {s.label}
        </span>
      ))}
    </div>
  )
}

function niceTicks(min: number, max: number, target: number): number[] {
  const span = max - min
  if (span <= 0) return [min]
  const raw = span / target
  const pow = Math.pow(10, Math.floor(Math.log10(raw)))
  const step = [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? raw
  const ticks: number[] = []
  for (let t = Math.ceil(min / step) * step; t <= max + 1e-9; t += step) {
    ticks.push(Number(t.toFixed(6)))
  }
  return ticks
}

// Une solo vueltas consecutivas: donde falta una (boxes, FCY...) la línea se corta.
function segments(points: Point[]): Point[][] {
  const sorted = [...points].sort((a, b) => a.x - b.x)
  const out: Point[][] = []
  let current: Point[] = []
  sorted.forEach((p, i) => {
    if (i > 0 && p.x - sorted[i - 1].x !== 1) {
      out.push(current)
      current = []
    }
    current.push(p)
  })
  if (current.length) out.push(current)
  return out
}

// Zoom y desplazamiento vertical (solo las gráficas con `interactiveY`).
const MIN_SPAN = 0.05 // s: zoom máximo (50 ms de rango visible)

type YView = { min: number; max: number }
type Geometry = { height: number; padTop: number; padBottom: number; full: YView; view: YView }

// Mantiene la ventana dentro del rango completo y con un tamaño válido.
function clampView(view: YView, full: YView): YView {
  const fullSpan = full.max - full.min
  const span = Math.min(Math.max(view.max - view.min, Math.min(MIN_SPAN, fullSpan)), fullSpan)
  const min = Math.min(Math.max(view.min, full.min), full.max - span)
  return { min, max: min + span }
}

// Cambia el tamaño de la ventana manteniendo `anchor` en la misma posición de pantalla.
function zoomView(view: YView, full: YView, factor: number, anchor: number): YView {
  const span = view.max - view.min
  const ratio = (anchor - view.min) / span
  const newSpan = span * factor
  const min = anchor - ratio * newSpan
  return clampView({ min, max: min + newSpan }, full)
}

function panView(view: YView, full: YView, delta: number): YView {
  return clampView({ min: view.min + delta, max: view.max + delta }, full)
}

// Valor (segundos) que corresponde a una posición vertical del SVG.
function valueAt(g: Geometry, yUnits: number): number {
  const plotH = g.height - g.padTop - g.padBottom
  return g.view.min + (1 - (yUnits - g.padTop) / plotH) * (g.view.max - g.view.min)
}

function LineChart({
  series,
  compact = false,
  label,
  bands = [],
  interactiveY = false,
  resetKey = "",
  xLabel = "Vuelta",
}: {
  series: Series[]
  compact?: boolean
  label: string
  bands?: Band[]
  xLabel?: string // nombre del eje X: "Vuelta" o "Vuelta del stint"
  interactiveY?: boolean // permite moverse y ampliar en el eje Y
  resetKey?: string // al cambiar, vuelve a mostrarse todo el rango
}) {
  const [hover, setHover] = useState<{ s: number; p: number } | null>(null)
  const [yView, setYView] = useState<YView | null>(null)
  const [dragging, setDragging] = useState(false)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const dragRef = useRef<{ startY: number; view: YView } | null>(null)
  const geom = useRef<Geometry | null>(null)
  const clipId = `clip-${useId().replace(/:/g, "")}`
  const all = series.flatMap((s) => s.points)
  const empty = all.length === 0

  // Al cambiar la selección se vuelve a ver todo el rango.
  useEffect(() => {
    setYView(null)
  }, [resetKey])

  // Ctrl (o ⌘) + rueda: ampliar/reducir alrededor del puntero. Sin Ctrl la rueda
  // sigue desplazando la página.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg || !interactiveY) return
    const onWheel = (event: WheelEvent) => {
      const g = geom.current
      if (!g || !(event.ctrlKey || event.metaKey)) return
      event.preventDefault()
      const rect = svg.getBoundingClientRect()
      if (!rect.height) return
      const anchor = valueAt(g, ((event.clientY - rect.top) / rect.height) * g.height)
      setYView(zoomView(g.view, g.full, event.deltaY < 0 ? 1 / 1.25 : 1.25, anchor))
    }
    svg.addEventListener("wheel", onWheel, { passive: false })
    return () => svg.removeEventListener("wheel", onWheel)
  }, [interactiveY, empty])

  if (empty) {
    geom.current = null
    return <p className="chart-empty">No hay vueltas que mostrar con los filtros actuales.</p>
  }

  const width = 620
  const height = compact ? 230 : 290
  const pad = { left: 74, right: 18, top: 14, bottom: 30 }
  const plotW = width - pad.left - pad.right
  const plotH = height - pad.top - pad.bottom

  const xs = [...all.map((p) => p.x), ...bands.flatMap((b) => [b.from - 0.5, b.to + 0.5])]
  const ys = all.map((p) => p.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const rawMinY = Math.min(...ys)
  const rawMaxY = Math.max(...ys)
  const margin = (rawMaxY - rawMinY || 1) * 0.08
  const full: YView = { min: rawMinY - margin, max: rawMaxY + margin }
  const view = interactiveY && yView ? clampView(yView, full) : full
  const zoomed = view.max - view.min < full.max - full.min - 1e-9
  const atMaxZoom = view.max - view.min <= MIN_SPAN + 1e-9
  geom.current = { height, padTop: pad.top, padBottom: pad.bottom, full, view }
  const minY = view.min
  const maxY = view.max

  const sx = (x: number) => pad.left + ((x - minX) / (maxX - minX || 1)) * plotW
  const sy = (y: number) => pad.top + (1 - (y - minY) / (maxY - minY)) * plotH
  const visible = (y: number) => y >= minY - 1e-9 && y <= maxY + 1e-9

  const yTicks = niceTicks(minY, maxY, 5)
  const xTicks = niceTicks(minX, maxX, 8).filter(Number.isInteger)

  const zoomBy = (factor: number) =>
    setYView(zoomView(view, full, factor, (view.min + view.max) / 2))
  const panBy = (fraction: number) =>
    setYView(panView(view, full, (view.max - view.min) * fraction))

  // Arrastrar: la gráfica sigue al puntero.
  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!interactiveY || event.button !== 0) return
    dragRef.current = { startY: event.clientY, view }
    setDragging(true)
    setHover(null)
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }
  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current
    if (!drag) return
    const rect = event.currentTarget.getBoundingClientRect()
    if (!rect.height) return
    const dyUnits = ((event.clientY - drag.startY) / rect.height) * height
    const delta = (dyUnits / plotH) * (drag.view.max - drag.view.min)
    setYView(panView(drag.view, full, delta))
  }
  const endDrag = () => {
    dragRef.current = null
    setDragging(false)
  }

  const hovered = hover ? series[hover.s]?.points[hover.p] : undefined
  const tooltip = hovered
    ? {
        left: Math.min(88, Math.max(12, (sx(hovered.x) / width) * 100)),
        top: (sy(hovered.y) / height) * 100,
      }
    : null

  return (
    <>
      {interactiveY && (
        <div className="chart-tools" role="group" aria-label="Zoom y desplazamiento vertical">
          <button
            type="button"
            onClick={() => zoomBy(1 / 1.5)}
            disabled={atMaxZoom}
            aria-label="Ampliar zona (zoom vertical)"
            title="Ampliar"
          >
            +
          </button>
          <button
            type="button"
            onClick={() => zoomBy(1.5)}
            disabled={!zoomed}
            aria-label="Reducir zoom vertical"
            title="Reducir"
          >
            −
          </button>
          <button
            type="button"
            onClick={() => panBy(0.25)}
            disabled={!zoomed}
            aria-label="Subir: ver tiempos más lentos"
            title="Subir"
          >
            ↑
          </button>
          <button
            type="button"
            onClick={() => panBy(-0.25)}
            disabled={!zoomed}
            aria-label="Bajar: ver tiempos más rápidos"
            title="Bajar"
          >
            ↓
          </button>
          <button type="button" onClick={() => setYView(null)} disabled={!zoomed}>
            Ver todo
          </button>
          <span className="chart-tools-hint">
            Arrastra para moverte · Ctrl + rueda para ampliar · doble clic para ver todo
          </span>
        </div>
      )}
      <div className="chart-wrap">
        <svg
          ref={svgRef}
          className={`line-chart${interactiveY ? " interactive" : ""}${dragging ? " dragging" : ""}`}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={label}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onDoubleClick={() => setYView(null)}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={pad.left} y={pad.top} width={plotW} height={plotH} />
            </clipPath>
          </defs>
          {bands.map((b, i) => {
            const x1 = sx(b.from - 0.5)
            const x2 = sx(b.to + 0.5)
            return (
              <g key={`band-${b.label}`}>
                <rect
                  x={x1}
                  y={pad.top}
                  width={x2 - x1}
                  height={plotH}
                  fill={i % 2 === 0 ? "rgba(66,214,255,0.07)" : "rgba(157,134,255,0.07)"}
                />
                <text
                  x={(x1 + x2) / 2}
                  y={pad.top + 13}
                  textAnchor="middle"
                  fill="#9fb0c2"
                  fontSize="11"
                >
                  {x2 - x1 < 54 ? b.short : b.label}
                </text>
              </g>
            )
          })}
          {yTicks.map((t) => (
            <g key={`y${t}`}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={sy(t)}
                y2={sy(t)}
                stroke="#203044"
                strokeWidth="1"
              />
              <text
                x={pad.left - 8}
                y={sy(t) + 4}
                textAnchor="end"
                fill="#8da0b4"
                fontSize="11"
              >
                {formatLapTime(t)}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text
              key={`x${t}`}
              x={sx(t)}
              y={height - 8}
              textAnchor="middle"
              fill="#8da0b4"
              fontSize="11"
            >
              {t}
            </text>
          ))}
          <text x={width - pad.right} y={height - 8} textAnchor="end" fill="#62758a" fontSize="10">
            {xLabel.toLowerCase()}
          </text>

          <g clipPath={interactiveY ? `url(#${clipId})` : undefined}>
            {series.map(
              (s) =>
                s.line &&
                (s.dashed ? [[...s.points].sort((a, b) => a.x - b.x)] : segments(s.points))
                  .filter((seg) => seg.length > 1)
                  .map((seg, i) => (
                    <polyline
                      key={`${s.id}-line-${i}`}
                      points={seg.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ")}
                      fill="none"
                      stroke={s.color}
                      strokeWidth={s.dashed ? 1.6 : 2}
                      strokeDasharray={s.dash ?? (s.dashed ? "6 4" : undefined)}
                      strokeOpacity={s.dashed ? 0.95 : 0.75}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  )),
            )}

            {series.map((s, si) =>
              s.markers === false
                ? null
                : s.points.map((p, pi) => {
                    if (!visible(p.y)) return null
                    const isHover = hover?.s === si && hover.p === pi
                    return (
                      <g key={`${s.id}-${p.x}-${pi}`}>
                        {p.best && (
                          <circle
                            cx={sx(p.x)}
                            cy={sy(p.y)}
                            r={8.5}
                            fill="none"
                            stroke="#FFFFFF"
                            strokeWidth="1.6"
                          />
                        )}
                        <Marker
                          shape={s.shape}
                          x={sx(p.x)}
                          y={sy(p.y)}
                          r={isHover ? 5.4 : 3.6}
                          color={s.color}
                        />
                        <circle
                          cx={sx(p.x)}
                          cy={sy(p.y)}
                          r={9}
                          fill="transparent"
                          onMouseEnter={() => setHover({ s: si, p: pi })}
                          onMouseLeave={() => setHover(null)}
                        />
                      </g>
                    )
                  }),
            )}
          </g>

          {interactiveY && zoomed && (
            <g aria-hidden="true">
              <rect x={width - 11} y={pad.top} width={5} height={plotH} rx={2.5} fill="#182536" />
              <rect
                x={width - 11}
                y={pad.top + (1 - (view.max - full.min) / (full.max - full.min)) * plotH}
                width={5}
                height={((view.max - view.min) / (full.max - full.min)) * plotH}
                rx={2.5}
                fill="#4b6a8c"
              />
            </g>
          )}
        </svg>

        {hovered && tooltip && (
          <div
            className={`chart-tooltip ${tooltip.top < 30 ? "below" : ""}`}
            style={{ left: `${tooltip.left}%`, top: `${tooltip.top}%` }}
          >
            <b>
              {xLabel} {hovered.x}
            </b>
            <strong>{formatLapTime(hovered.y)}</strong>
            <span>{hovered.who}</span>
            {hovered.best && <em>Mejor vuelta de la serie</em>}
            {hovered.note && <em>{hovered.note}</em>}
          </div>
        )}
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Construcción de series a partir de los datos del backend
// ---------------------------------------------------------------------------
function markBest(points: Point[]): Point[] {
  if (!points.length) return points
  const best = Math.min(...points.map((p) => p.y))
  return points.map((p) => (p.y === best ? { ...p, best: true } : p))
}

function lapPoints(data: CarData, pace: boolean, driver?: string): Point[] {
  return data.laps.flatMap((l) =>
    l.seconds === null || l.isPace !== pace || (driver !== undefined && l.driver !== driver)
      ? []
      : [{ x: l.lap, y: l.seconds, who: l.driver, note: pace ? undefined : l.status }],
  )
}

function excludedSeries(data: CarData, mode: Mode): Series[] {
  if (mode !== "todas") return []
  const points = lapPoints(data, false)
  if (!points.length) return []
  return [
    {
      id: "excluded",
      label: "Vueltas excluidas (boxes, FCY, lentas)",
      color: EXCLUDED_COLOR,
      shape: "cross",
      line: false,
      points,
    },
  ]
}

function driverSeries(data: CarData, mode: Mode): Series[] {
  return [
    ...data.drivers.map((driver, i) => ({
      id: driver.name,
      label: driver.name,
      color: DRIVER_PALETTE[i % DRIVER_PALETTE.length],
      shape: SHAPES[i % SHAPES.length],
      line: true,
      points: markBest(lapPoints(data, true, driver.name)),
    })),
    ...excludedSeries(data, mode),
  ]
}

// Superpuesto: cada stint de cada piloto empieza en la vuelta 1 (salida de boxes), de modo
// que los ritmos de los pilotos se ven unos encima de otros. El color y la forma
// identifican al piloto; el trazo, el stint cuando un mismo piloto tiene varios.
const STINT_DASHES = [undefined, "7 4", "2 4", "10 3 2 3"]

function overlaySeries(data: CarData, mode: Mode): Series[] {
  const out: Series[] = []
  data.drivers.forEach((driver, di) => {
    const color = DRIVER_PALETTE[di % DRIVER_PALETTE.length]
    const shape = SHAPES[di % SHAPES.length]
    const mine = data.laps.filter((l) => l.driver === driver.name)
    const stints = [...new Set(mine.map((l) => l.stint))].sort((a, b) => a - b)
    const bestY = Math.min(
      ...mine.flatMap((l) => (l.isPace && l.seconds !== null ? [l.seconds] : [])),
    )
    stints.forEach((stint, si) => {
      const points: Point[] = mine.flatMap((l) =>
        l.stint !== stint || !l.isPace || l.seconds === null
          ? []
          : [
              {
                x: l.stintLap,
                y: l.seconds,
                who: driver.name,
                note: `Vuelta ${l.lap} de carrera · Stint ${stint}`,
                best: l.seconds === bestY,
              },
            ],
      )
      if (!points.length) return
      out.push({
        id: `${driver.name}-s${stint}`,
        label: stints.length > 1 ? `${driver.name} · Stint ${stint}` : driver.name,
        color,
        shape,
        line: true,
        dash: STINT_DASHES[si % STINT_DASHES.length],
        points,
      })
    })
  })
  if (mode === "todas") {
    const points: Point[] = data.laps.flatMap((l) =>
      l.isPace || l.seconds === null
        ? []
        : [
            {
              x: l.stintLap,
              y: l.seconds,
              who: l.driver,
              note: `Vuelta ${l.lap} de carrera · Stint ${l.stint} · ${l.status}`,
            },
          ],
    )
    if (points.length)
      out.push({
        id: "excluded",
        label: "Vueltas excluidas (boxes, FCY, lentas)",
        color: EXCLUDED_COLOR,
        shape: "cross",
        line: false,
        points,
      })
  }
  return out
}

// Coches marcados en la clasificación para comparar su ritmo (máx. 4). Cada uno
// conserva su color y su forma (`slot`) mientras siga seleccionado.
type Selection = { car: string; slot: number }
const MAX_COMPARE = 4

function paceSeries(data: CategoryData, picks: Selection[]): Series[] {
  return picks.flatMap(({ car, slot }) => {
    const item = data.pace.find((p) => p.car === car)
    if (!item) return []
    return [
      {
        id: car,
        label: `#${car} ${item.team}`,
        color: PALETTE[slot % PALETTE.length],
        shape: SHAPES[slot % SHAPES.length],
        line: true,
        points: markBest(
          item.laps.flatMap((l) =>
            l.seconds === null ? [] : [{ x: l.lap, y: l.seconds, who: l.driver }],
          ),
        ),
      },
    ]
  })
}

function csvCell(value: string | number): string {
  const text = String(value)
  return /[";\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

// ---------------------------------------------------------------------------
// Pantallas
// ---------------------------------------------------------------------------
function Header({
  categoryLabel,
  onHome,
}: {
  categoryLabel?: string
  onHome?: () => void
}) {
  return (
    <header className="topbar">
      <Logo onClick={onHome} />
      <div className="top-actions">
        {categoryLabel && (
          <span className="breadcrumb">
            Análisis <i>/</i> {categoryLabel}
          </span>
        )}
        <span className="live-pill">
          <i /> SESIÓN IMPORTADA
        </span>
        <span className="avatar">BG</span>
      </div>
    </header>
  )
}

function Footer({ sessionName }: { sessionName?: string }) {
  return (
    <footer>
      <span>
        {sessionName ? `Datos reales · ${sessionName}` : "Datos reales de sesión"}
      </span>
      <span>WEC · 2026 · BG</span>
    </footer>
  )
}

function Status({
  title,
  detail,
  busy = false,
}: {
  title: string
  detail?: string
  busy?: boolean
}) {
  return (
    <div className="app-shell">
      <Header />
      <main className="status" role={busy ? "status" : "alert"}>
        <h1>{title}</h1>
        {detail && <p>{detail}</p>}
      </main>
      <Footer />
    </div>
  )
}

function SessionSelect({
  sessions,
  value,
  onChange,
  className,
  category,
  categoryLabel,
}: {
  sessions: SessionInfo[]
  value: string
  onChange: (id: string) => void
  className: string
  category?: string // si se indica, solo se pueden elegir sesiones que tengan esa categoría
  categoryLabel?: string
}) {
  return (
    <label className={className}>
      <span className="select-label">Sesión</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {sessions.map((s) => {
          const unavailable =
            category !== undefined && s.categories !== null && !s.categories.includes(category)
          return (
            <option key={s.id} value={s.id} disabled={unavailable}>
              {s.name}
              {unavailable ? ` — sin ${categoryLabel ?? category}` : ""}
            </option>
          )
        })}
      </select>
    </label>
  )
}

function Landing({
  overview,
  sessions,
  sessionId,
  onSession,
  onSelect,
}: {
  overview: Overview
  sessions: SessionInfo[]
  sessionId: string
  onSession: (id: string) => void
  onSelect: (category: string) => void
}) {
  return (
    <div className="app-shell landing-shell">
      <Header />
      <main className="landing">
        <div className="eyebrow">
          <span /> WEC / CENTRO DE ANÁLISIS
        </div>
        <h1>Cada vuelta cuenta.</h1>
        <p className="intro">
          Selecciona una categoría. Descubre el ritmo de cada coche y lo que
          marca la diferencia entre sus pilotos.
        </p>
        <SessionSelect
          className="session-select"
          sessions={sessions}
          value={sessionId}
          onChange={onSession}
        />
        <div className="category-grid">
          {overview.categories.map((category) => {
            const copy = categoryCopy[category.id] ?? fallbackCopy
            return (
              <article className="category-card" key={category.id}>
                <div className="category-image">
                  <img
                    src={photos[category.id.toLowerCase()] ?? photos.hypercar}
                    alt={`Coche de competición de la categoría ${category.label}`}
                  />
                  <div className="image-shade" />
                  <span className="category-tag">{copy.badge}</span>
                  <div className="image-title">
                    <h2>{category.label}</h2>
                    <span>WEC 2026</span>
                  </div>
                </div>
                <div className="category-copy">
                  <p>{copy.description}</p>
                  <div className="category-stats">
                    {category.cars} coches · {category.drivers} pilotos · mejor
                    vuelta {category.bestLap.text}
                  </div>
                  <button
                    className="primary-button"
                    onClick={() => onSelect(category.id)}
                  >
                    Analizar {category.label}
                    <Icon name="chevron" size={16} />
                  </button>
                </div>
              </article>
            )
          })}
        </div>
        <div className="event-strip">
          <span className="event-icon">
            <Icon name="flag" />
          </span>
          <div>
            <small>SESIÓN CARGADA</small>
            <strong>{overview.session.name}</strong>
          </div>
          <div className="event-meta">
            <span>{overview.laps.toLocaleString("es-ES")} vueltas</span>
            <b>
              {overview.clockStart} – {overview.clockEnd}
            </b>
          </div>
        </div>
      </main>
      <Footer sessionName={overview.session.name} />
    </div>
  )
}

function MetricCard({
  label,
  value,
  note,
  detail,
  accent,
}: {
  label: string
  value: string
  note: string
  detail: string
  accent?: boolean
}) {
  return (
    <div className={`metric-card ${accent ? "metric-accent" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small className="metric-note">{note}</small>
      <small className="metric-detail">{detail}</small>
    </div>
  )
}

// Evolución del ritmo de un piloto durante sus stints (vuelta en X, tiempo en Y).
function StintPanel({ data }: { data: CarData }) {
  const [driver, setDriver] = useState(data.drivers[0]?.name ?? "")
  const [showTrend, setShowTrend] = useState(false)
  const [showExcluded, setShowExcluded] = useState(false)

  const index = Math.max(0, data.drivers.findIndex((d) => d.name === driver))
  const color = DRIVER_PALETTE[index % DRIVER_PALETTE.length]
  const shape = SHAPES[index % SHAPES.length]
  const stints = data.stints.filter((s) => s.driver === driver)

  const series = useMemo<Series[]>(() => {
    const laps = data.laps.filter((l) => l.driver === driver)
    const toPoint = (l: (typeof laps)[number]): Point[] =>
      l.seconds === null
        ? []
        : [
            {
              x: l.lap,
              y: l.seconds,
              who: driver,
              note: `Stint ${l.stint} · vuelta ${l.stintLap} del stint${l.isPace ? "" : ` · ${l.status}`}`,
            },
          ]
    const out: Series[] = [
      {
        id: "pace",
        label: "Vueltas de ritmo",
        color,
        shape,
        line: true,
        points: markBest(laps.filter((l) => l.isPace).flatMap(toPoint)),
      },
    ]
    if (showTrend) {
      for (const stint of stints) {
        if (!stint.trend) continue
        const inStint = laps.filter((l) => l.stint === stint.stint && l.isPace)
        if (inStint.length < 2) continue
        const first = inStint[0]
        const last = inStint[inStint.length - 1]
        const at = (stintLap: number) => stint.trend!.intercept + stint.trend!.slope * stintLap
        out.push({
          id: `trend-${stint.stint}`,
          label: "Tendencia por stint",
          color: "#E6EDF5",
          shape: "circle",
          line: true,
          dashed: true,
          markers: false,
          points: [
            { x: first.lap, y: at(first.stintLap), who: driver },
            { x: last.lap, y: at(last.stintLap), who: driver },
          ],
        })
      }
    }
    if (showExcluded) {
      const excluded = laps.filter((l) => !l.isPace).flatMap(toPoint)
      if (excluded.length) {
        out.push({
          id: "excluded",
          label: "Vueltas excluidas (boxes, FCY, lentas)",
          color: EXCLUDED_COLOR,
          shape: "cross",
          line: false,
          points: excluded,
        })
      }
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, driver, showTrend, showExcluded])

  const bands: Band[] = stints.map((s) => ({
    from: s.startLap,
    to: s.endLap,
    label: `Stint ${s.stint}`,
    short: `S${s.stint}`,
  }))
  const legend = series.filter((s, i, all) => all.findIndex((t) => t.label === s.label) === i)

  return (
    <section className="stint-section" id="stint">
      <div className="section-title">
        <div>
          <div className="eyebrow">
            <span /> EVOLUCIÓN EN EL STINT
          </div>
          <h2>Gráfico ritmo por vuelta</h2>
          <p>Elige un piloto del coche para ver cómo evoluciona su ritmo durante cada stint.</p>
        </div>
        <label className="car-select">
          <span>PILOTO</span>
          <select value={driver} onChange={(event) => setDriver(event.target.value)}>
            {data.drivers.map((d) => (
              <option key={d.name} value={d.name}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <article className="panel stint-panel">
        <div className="stint-controls">
          <label className="check">
            <input
              type="checkbox"
              checked={showTrend}
              onChange={(event) => setShowTrend(event.target.checked)}
            />
            Tendencia por stint
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={showExcluded}
              onChange={(event) => setShowExcluded(event.target.checked)}
            />
            Mostrar vueltas excluidas
          </label>
        </div>
        <div className="stint-body">
          <div className="chart-head">
            <h3>
              {driver} · coche #{data.car.number}
            </h3>
            <span>{timeFormatLabel()} ↓</span>
          </div>
          <Legend series={legend} />
          <LineChart
            series={series}
            bands={bands}
            label={`Ritmo por vuelta de ${driver} en el coche ${data.car.number}, por stint`}
          />
          <p className="chart-note">
            Las franjas marcan cada stint: desde la vuelta de salida de boxes hasta la de
            entrada. El círculo blanco señala la mejor vuelta.
          </p>

          <div className="table-scroll stint-table">
            <table>
              <caption className="sr-only">Stints de {driver}</caption>
              <thead>
                <tr>
                  <th scope="col">Stint</th>
                  <th scope="col">Vueltas</th>
                  <th scope="col">De ritmo</th>
                  <th scope="col">Mejor vuelta</th>
                  <th scope="col">Ritmo medio</th>
                  <th scope="col">Tendencia</th>
                </tr>
              </thead>
              <tbody>
                {stints.map((s) => (
                  <tr key={s.stint}>
                    <td>{s.stint}</td>
                    <td>
                      {s.startLap}–{s.endLap} ({s.laps})
                    </td>
                    <td>{s.paceLaps}</td>
                    <td>{s.best.text}</td>
                    <td>{s.median.text}</td>
                    <td>{s.trend ? `${formatSigned(s.trend.slope)} s/vuelta` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="chart-note">
            Ritmo medio = mediana de las vueltas de ritmo. La tendencia es la pendiente del
            tiempo de vuelta dentro del stint (positiva = el ritmo cae) y se calcula con al
            menos 3 vueltas de ritmo. Mezcla neumáticos, combustible y tráfico: úsala como
            orientación, sobre todo en sesiones de libres.
          </p>
        </div>
      </article>
    </section>
  )
}

function Dashboard({
  sessionId,
  sessionName,
  sessions,
  onSession,
  slow,
  onSlow,
  category,
  categories,
  onCategory,
  onHome,
}: {
  sessionId: string
  sessionName: string
  sessions: SessionInfo[]
  onSession: (id: string) => void
  slow: number
  onSlow: (pct: number) => void
  category: string
  categories: { id: string; label: string }[]
  onCategory: (category: string) => void
  onHome: () => void
}) {
  const [metric, setMetric] = useState<Metric>("lap")
  const [mode, setMode] = useState<Mode>("ritmo")
  const [overlay, setOverlay] = useState(false)
  const [selectedCar, setSelectedCar] = useState<string | null>(null)
  const [compare, setCompare] = useState<Selection[]>([])

  const cat = useApi(() => api.category(sessionId, category, slow), [sessionId, category, slow])
  const car = useApi(
    selectedCar ? () => api.car(sessionId, selectedCar, slow) : null,
    [sessionId, selectedCar, slow],
  )

  // Coche por defecto: el más rápido de la categoría.
  useEffect(() => {
    const data = cat.data
    if (!data) return
    setSelectedCar((current) =>
      current && data.cars.some((c) => c.number === current)
        ? current
        : (data.rankings.lap[0]?.car ?? data.cars[0]?.number ?? null),
    )
  }, [cat.data])

  // Por defecto se comparan los más rápidos; si cambian de categoría, se vuelve a ese valor.
  const activeCompare = useMemo<Selection[]>(() => {
    const data = cat.data
    if (!data) return []
    const valid = compare.filter((c) => data.cars.some((x) => x.number === c.car))
    return valid.length
      ? valid
      : data.rankings.lap.slice(0, MAX_COMPARE).map((r, slot) => ({ car: r.car, slot }))
  }, [cat.data, compare])
  const paceChartSeries = useMemo<Series[]>(
    () => (cat.data ? paceSeries(cat.data, activeCompare) : []),
    [cat.data, activeCompare],
  )
  const compareSeries = useMemo(
    () =>
      car.data ? (overlay ? overlaySeries(car.data, mode) : driverSeries(car.data, mode)) : [],
    [car.data, mode, overlay],
  )

  if (cat.error) return <Status title="No se pudieron cargar los datos" detail={cat.error} />
  if (!cat.data) return <Status busy title="Cargando datos…" />

  const data = cat.data
  const ranking = data.rankings[metric]
  const metricTitle = METRIC_TABS.find((t) => t.key === metric)?.title ?? ""
  const carOption = data.cars.find((c) => c.number === selectedCar)

  function exportCsv(rows: RankingRow[]) {
    const lines = [
      ["Posición", "Coche", "Equipo", "Piloto", metricTitle, "Diferencia", "Vuelta", "Hora"],
      ...rows.map((r) => [r.position, r.car, r.team, r.driver, r.text, r.gapText, r.lap, r.clock]),
    ].map((line) => line.map(csvCell).join(";"))
    const url = URL.createObjectURL(
      new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" }),
    )
    const link = document.createElement("a")
    link.href = url
    link.download = `race-strategy-${category.toLowerCase()}-${metric}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  function changeCategory(next: string) {
    setSelectedCar(null)
    setCompare([])
    onCategory(next)
  }

  function toggleCar(car: string) {
    const existing = activeCompare.find((c) => c.car === car)
    if (existing) {
      if (activeCompare.length > 1) setCompare(activeCompare.filter((c) => c.car !== car))
      return
    }
    if (activeCompare.length >= MAX_COMPARE) return
    const used = new Set(activeCompare.map((c) => c.slot))
    const slot = Array.from({ length: MAX_COMPARE }, (_, i) => i).find((i) => !used.has(i)) ?? 0
    setCompare([...activeCompare, { car, slot }])
  }

  const drivers = car.data?.drivers ?? []
  const fastest = drivers.reduce<number | null>(
    (best, d) =>
      d.best.seconds !== null && (best === null || d.best.seconds < best) ? d.best.seconds : best,
    null,
  )
  const leader = drivers.find((d) => d.best.seconds === fastest)
  // Barras de diferencia de ritmo: escala común a todos los pilotos, mínimo 0,6 s.
  const maxGap = drivers.reduce((max, d) => Math.max(max, d.medianGap.seconds ?? 0), 0)
  const scaleMax = Math.max(0.6, Math.ceil(maxGap * 10) / 10)

  return (
    <div className="app-shell dashboard-shell">
      <Header categoryLabel={data.category.label} onHome={onHome} />
      <aside className="sidebar" aria-label="Navegación de análisis">
        <button className="active" aria-label="Resumen">
          <Icon name="chart" />
        </button>
        <a href="#ranking" aria-label="Clasificación">
          <Icon name="grid" />
        </a>
        <a href="#drivers" aria-label="Pilotos">
          <Icon name="clock" />
        </a>
      </aside>
      <main className="dashboard">
        <section className="dashboard-heading">
          <div>
            <div className="eyebrow">
              <span /> ANÁLISIS DE RENDIMIENTO
            </div>
            <div className="title-row">
              <h1>Análisis {data.category.label}</h1>
              <span className="sample-badge">{sessionName}</span>
            </div>
          </div>
          <div className="heading-actions">
            <label>
              <span className="sr-only">Cambiar categoría</span>
              <select
                value={category}
                onChange={(event) => changeCategory(event.target.value)}
              >
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <button onClick={() => exportCsv(ranking)}>
              Exportar informe <Icon name="download" size={15} />
            </button>
          </div>
        </section>

        <section className="filter-row" aria-label="Filtros del análisis">
          <SessionSelect
            className="filter-select"
            sessions={sessions}
            value={sessionId}
            onChange={onSession}
            category={category}
            categoryLabel={data.category.label}
          />
          <label className="filter-select">
            <span className="select-label">Vuelta lenta</span>
            <select value={slow} onChange={(event) => onSlow(Number(event.target.value))}>
              {SLOW_OPTIONS.map((pct) => (
                <option key={pct} value={pct}>
                  más del {pct} % de la mejor
                </option>
              ))}
            </select>
          </label>
          <span className="data-count">
            {data.counts.laps.toLocaleString("es-ES")} vueltas / {data.counts.drivers} pilotos /{" "}
            {data.counts.cars} coches
          </span>
        </section>

        <div className="tabs" role="tablist" aria-label="Métrica de la clasificación">
          {METRIC_TABS.map((tab) => (
            <button
              key={tab.key}
              role="tab"
              aria-selected={metric === tab.key}
              className={metric === tab.key ? "active" : ""}
              onClick={() => setMetric(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <section className="metrics-grid" aria-label="Mejores tiempos de la categoría">
          {data.bests.map((best) => (
            <MetricCard
              key={best.key}
              label={`${best.label} de la categoría`}
              value={best.text}
              note={`#${best.car} · ${best.driver}`}
              detail={`${best.team} · vuelta ${best.lap} · ${best.clock} (sesión ${best.elapsed})`}
              accent={best.key === "lap"}
            />
          ))}
        </section>

        <section className="analysis-grid">
          <article className="panel pace-panel">
            <div className="panel-heading">
              <div>
                <h2>Evolución del ritmo</h2>
                <p aria-live="polite">
                  {activeCompare.length} de {MAX_COMPARE} coches · vueltas de ritmo · elige los
                  coches en la clasificación
                </p>
              </div>
              <span className="panel-unit">TIEMPO / VUELTA</span>
            </div>
            <Legend series={paceChartSeries} />
            <LineChart
              series={paceChartSeries}
              interactiveY
              resetKey={`${category}|${activeCompare.map((c) => c.car).join(",")}`}
              label="Tiempo por vuelta de los coches seleccionados de la categoría"
            />
          </article>

          <article className="panel ranking-panel" id="ranking">
            <div className="panel-heading">
              <div>
                <h2>Clasificación por {metric === "lap" ? "ritmo" : "sector"}</h2>
                <p>{metricTitle} · marca hasta {MAX_COMPARE} coches para comparar</p>
              </div>
              <span className="panel-unit">{ranking.length} COCHES</span>
            </div>
            <ol className="ranking-list" tabIndex={0} aria-label={`Clasificación: ${metricTitle}`}>
              {ranking.map((row, index) => {
                const pick = activeCompare.find((c) => c.car === row.car)
                const atMax = !pick && activeCompare.length >= MAX_COMPARE
                const onlyOne = !!pick && activeCompare.length === 1
                return (
                  <li
                    key={row.car}
                    className={`${index === 0 ? "leader" : ""} ${pick ? "selected" : ""}`}
                  >
                    <input
                      type="checkbox"
                      className="compare-check"
                      checked={!!pick}
                      disabled={atMax || onlyOne}
                      title={
                        atMax
                          ? `Máximo ${MAX_COMPARE} coches`
                          : onlyOne
                            ? "Debe quedar al menos un coche"
                            : undefined
                      }
                      onChange={() => toggleCar(row.car)}
                      aria-label={`Comparar el ritmo del coche #${row.car} ${row.team}`}
                    />
                    <span className="rank">{String(row.position).padStart(2, "0")}</span>
                    <span className="team">
                      {pick && (
                        <svg
                          className="team-swatch"
                          width="12"
                          height="12"
                          viewBox="0 0 12 12"
                          aria-hidden="true"
                        >
                          <Marker
                            shape={SHAPES[pick.slot % SHAPES.length]}
                            x={6}
                            y={6}
                            r={3.4}
                            color={PALETTE[pick.slot % PALETTE.length]}
                          />
                        </svg>
                      )}
                      #{row.car} {row.team}
                      <small>
                        {row.driver} · vuelta {row.lap}
                      </small>
                    </span>
                    <strong>{row.text}</strong>
                    <small className="delta">{row.gapText}</small>
                  </li>
                )
              })}
            </ol>
          </article>
        </section>

        <div className="insight-bar">
          <span>i</span>
          <p>
            <strong>Lectura rápida:</strong> {data.counts.paceLaps} de{" "}
            {data.counts.laps} vueltas de la categoría cuentan como ritmo. Se
            excluyen las de entrada y salida de boxes, las de bandera FCY y las
            que superan el {slow} % de la mejor vuelta de su coche.
          </p>
        </div>

        <section className="drivers-section" id="drivers">
          <div className="section-title">
            <div>
              <div className="eyebrow">
                <span /> COMPARATIVA INTERNA
              </div>
              <h2>Dentro del mismo coche</h2>
              <p>Selecciona un coche y compara el ritmo de sus pilotos.</p>
            </div>
            <label className="car-select">
              <span>COCHE</span>
              <select
                value={selectedCar ?? ""}
                onChange={(event) => setSelectedCar(event.target.value)}
              >
                {data.cars.map((c) => (
                  <option value={c.number} key={c.number}>
                    #{c.number} · {c.team}
                    {c.manufacturer ? ` · ${c.manufacturer}` : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <article className="panel driver-panel">
            {car.error && <p className="chart-empty">{car.error}</p>}
            {!car.data && !car.error && <p className="chart-empty">Cargando coche…</p>}
            {car.data && (
              <>
                <div className="car-header">
                  <span className="car-number">{car.data.car.number}</span>
                  <div>
                    <strong>{car.data.car.team}</strong>
                    <small>{car.data.car.manufacturer || carOption?.team}</small>
                  </div>
                  <span className="driver-count">
                    {car.data.drivers.length} PILOTOS · {car.data.counts.laps} VUELTAS
                  </span>
                  <div className="mode-switch" role="group" aria-label="Vueltas a mostrar">
                    <button
                      className={mode === "ritmo" ? "active" : ""}
                      aria-pressed={mode === "ritmo"}
                      onClick={() => setMode("ritmo")}
                    >
                      Ritmo
                    </button>
                    <button
                      className={mode === "todas" ? "active" : ""}
                      aria-pressed={mode === "todas"}
                      onClick={() => setMode("todas")}
                    >
                      Todas las vueltas
                    </button>
                  </div>
                </div>

                <div className="driver-content">
                  <div className="driver-chart">
                    <div className="chart-block">
                      <div className="chart-head">
                        <h3>Ritmo por vuelta</h3>
                        <span>{timeFormatLabel()} ↓</span>
                      </div>
                      <label className="check overlay-toggle">
                        <input
                          type="checkbox"
                          checked={overlay}
                          onChange={(event) => setOverlay(event.target.checked)}
                        />
                        Superponer pilotos
                      </label>
                      <Legend series={compareSeries} />
                      <LineChart
                        series={compareSeries}
                        xLabel={overlay ? "Vuelta del stint" : "Vuelta"}
                        label={`Tiempo por vuelta de los pilotos del coche ${car.data.car.number}${overlay ? ", superpuestos por vuelta del stint" : ""}`}
                      />
                    </div>
                    <p className="chart-note">
                      {overlay
                        ? "Cada stint empieza en la vuelta 1 (salida de boxes) para ver los ritmos de los pilotos unos encima de otros. Si un piloto tiene varios stints, se distinguen por el trazo. El círculo blanco marca la mejor vuelta de cada piloto."
                        : "El círculo blanco marca la mejor vuelta de cada piloto."}
                    </p>
                  </div>

                  <div className="driver-summary">
                    <div className="summary-head">
                      <h3>Ritmo medio por piloto</h3>
                      <span>Δ al más rápido</span>
                    </div>
                    {drivers.map((driver, index) => {
                      const color = DRIVER_PALETTE[index % DRIVER_PALETTE.length]
                      const gap = driver.medianGap.seconds
                      return (
                        <div className="pace-row" key={driver.name}>
                          <span className="pace-swatch" style={{ background: color }} />
                          <div className="pace-name">
                            <strong>{driver.name}</strong>
                            <small>
                              Mejor vuelta {driver.best.text} ({driver.deltaText})
                            </small>
                            <small>
                              S1 {driver.s1.text} · S2 {driver.s2.text} · S3 {driver.s3.text}
                            </small>
                          </div>
                          <div className="pace-value">
                            <span style={{ color }}>{driver.median.text}</span>
                            <small>{driver.medianGap.text}</small>
                          </div>
                          <div className="pace-track" aria-hidden="true">
                            <i
                              style={{
                                width: `${gap === null ? 0 : Math.max(2, (gap / scaleMax) * 100)}%`,
                                background: color,
                              }}
                            />
                          </div>
                        </div>
                      )
                    })}
                    <p className="summary-note">
                      Barras: diferencia de tiempo · escala común 0–{formatSeconds(scaleMax)} s
                    </p>
                    <p className="summary-note">
                      Vueltas de ritmo: {drivers.map((d) => `${d.name} ${d.paceLaps}`).join(" · ")}.
                      El ritmo medio es la mediana de las vueltas de ritmo; menor tiempo indica
                      mayor ritmo.
                    </p>
                  </div>
                </div>

                {leader && (
                  <div className="driver-insight">
                    <span>↗</span>
                    <p>
                      <strong>{leader.name}</strong> marca la mejor vuelta del coche (
                      {leader.best.text}) con una mediana de ritmo de {leader.median.text}.
                    </p>
                  </div>
                )}

                <details className="lap-table">
                  <summary>Ver todas las vueltas del coche como tabla</summary>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th scope="col">Vuelta</th>
                          <th scope="col">Piloto</th>
                          <th scope="col">Tiempo</th>
                          <th scope="col">S1</th>
                          <th scope="col">S2</th>
                          <th scope="col">S3</th>
                          <th scope="col">Hora</th>
                          <th scope="col">Estado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {car.data.laps.map((lap) => (
                          <tr key={lap.lap}>
                            <td>{lap.lap}</td>
                            <td>{lap.driver}</td>
                            <td>{lap.text}</td>
                            <td>{lap.s1}</td>
                            <td>{lap.s2}</td>
                            <td>{lap.s3}</td>
                            <td>{lap.clock}</td>
                            <td>{lap.status}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </>
            )}
          </article>
        </section>

        {car.data && <StintPanel key={car.data.car.number} data={car.data} />}
      </main>
      <Footer sessionName={sessionName} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// App: arranque, sesión activa y navegación inicio <-> análisis
// ---------------------------------------------------------------------------
export default function App() {
  const boot = useApi(api.sessions, [])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [slow, setSlow] = useState(107)
  const [category, setCategory] = useState<string | null>(null)

  useEffect(() => {
    if (!boot.data) return
    setMsSeparator(boot.data.settings.msSeparator)
    setSlow(boot.data.settings.slowThresholdPct)
    setSessionId((current) => current ?? boot.data?.sessions[0]?.id ?? null)
  }, [boot.data])

  const overview = useApi(sessionId ? () => api.overview(sessionId) : null, [sessionId])

  if (boot.error) return <Status title="No se pudo conectar con el backend" detail={boot.error} />
  if (!boot.data) return <Status busy title="Conectando con el backend…" />
  if (boot.data.sessions.length === 0) {
    return (
      <Status
        title="No hay sesiones para analizar"
        detail={`No se han encontrado archivos CSV o Excel en ${boot.data.dataDir}`}
      />
    )
  }
  if (overview.error) return <Status title="No se pudo cargar la sesión" detail={overview.error} />
  if (!sessionId || !overview.data) return <Status busy title="Importando la sesión…" />

  if (!category) {
    return (
      <Landing
        overview={overview.data}
        sessions={boot.data.sessions}
        sessionId={sessionId}
        onSession={setSessionId}
        onSelect={setCategory}
      />
    )
  }

  return (
    <Dashboard
      sessionId={sessionId}
      sessionName={overview.data.session.name}
      sessions={boot.data.sessions}
      onSession={setSessionId}
      slow={slow}
      onSlow={setSlow}
      category={category}
      categories={overview.data.categories}
      onCategory={setCategory}
      onHome={() => setCategory(null)}
    />
  )
}
