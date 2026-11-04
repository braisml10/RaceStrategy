import { useEffect, useState } from "react"
import {
  api,
  formatLapTime,
  setMsSeparator,
  useApi,
  type Metric,
} from "./api"

const metrics: { id: Metric; label: string }[] = [
  { id: "lap", label: "Vuelta" },
  { id: "s1", label: "Sector 1" },
  { id: "s2", label: "Sector 2" },
  { id: "s3", label: "Sector 3" },
]

export default function App() {
  const sessionsState = useApi(() => api.sessions(), [])
  const [sessionId, setSessionId] = useState("")
  const [categoryId, setCategoryId] = useState("")
  const [carNumber, setCarNumber] = useState("")
  const [metric, setMetric] = useState<Metric>("lap")

  const sessions = sessionsState.data?.sessions ?? []
  const session = sessions.find((item) => item.id === sessionId) ?? sessions[0]
  const activeSessionId = session?.id ?? ""
  const slowPct = sessionsState.data?.settings.slowThresholdPct ?? 107

  const overviewState = useApi(
    activeSessionId ? () => api.overview(activeSessionId) : null,
    [activeSessionId],
  )

  const categories = overviewState.data?.categories ?? []
  const category =
    categories.find((item) => item.id === categoryId) ?? categories[0]
  const activeCategoryId = category?.id ?? ""

  const categoryState = useApi(
    activeSessionId && activeCategoryId
      ? () => api.category(activeSessionId, activeCategoryId, slowPct)
      : null,
    [activeSessionId, activeCategoryId, slowPct],
  )

  const cars = categoryState.data?.cars ?? []
  const selectedCar = cars.find((car) => car.number === carNumber) ?? cars[0]
  const activeCarNumber = selectedCar?.number ?? ""

  const carState = useApi(
    activeSessionId && activeCarNumber
      ? () => api.car(activeSessionId, activeCarNumber, slowPct)
      : null,
    [activeSessionId, activeCarNumber, slowPct],
  )

  useEffect(() => {
    const separator = sessionsState.data?.settings.msSeparator
    if (separator) setMsSeparator(separator)
  }, [sessionsState.data])

  if (sessionsState.loading) {
    return <main className="backend-message">Cargando sesiones…</main>
  }

  if (sessionsState.error) {
    return (
      <main className="backend-message backend-error">
        <h1>No se pudo cargar el backend</h1>
        <p>{sessionsState.error}</p>
        <p>
          Comprueba que Uvicorn siga activo en el puerto 8000 y abre{" "}
          <a href="http://localhost:8000/docs" target="_blank">
            la documentación de la API
          </a>
          .
        </p>
      </main>
    )
  }

  if (sessions.length === 0) {
    return (
      <main className="backend-message">
        <h1>Race Strategy</h1>
        <p>El backend responde, pero no encuentra archivos de sesión.</p>
        <p>
          Coloca los CSV o Excel en la carpeta de datos configurada por el
          backend y vuelve a cargar la página.
        </p>
        {sessionsState.data?.dataDir && (
          <code>{sessionsState.data.dataDir}</code>
        )}
      </main>
    )
  }

  return (
    <div className="backend-app">
      <header className="backend-header">
        <a className="backend-brand" href="#">
          <span className="backend-mark">R</span>
          <span>RACE STRATEGY</span>
        </a>

        <label className="backend-session">
          Sesión
          <select
            value={activeSessionId}
            onChange={(event) => {
              setSessionId(event.target.value)
              setCategoryId("")
              setCarNumber("")
            }}
          >
            {sessions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      </header>

      <main className="backend-main">
        <section className="backend-heading">
          <div>
            <p className="backend-eyebrow">ANÁLISIS DE CARRERA</p>
            <h1>{session?.name ?? "Sesión"}</h1>
          </div>
          {overviewState.data && (
            <p className="backend-summary">
              {overviewState.data.laps} vueltas · {overviewState.data.cars} coches
              · {overviewState.data.drivers} pilotos
            </p>
          )}
        </section>

        {overviewState.loading && <p>Cargando resumen…</p>}
        {overviewState.error && (
          <p className="backend-error">Error al cargar la sesión: {overviewState.error}</p>
        )}

        {categories.length > 0 && (
          <nav className="backend-tabs" aria-label="Categorías">
            {categories.map((item) => (
              <button
                key={item.id}
                className={item.id === activeCategoryId ? "active" : ""}
                onClick={() => {
                  setCategoryId(item.id)
                  setCarNumber("")
                }}
              >
                {item.label}
              </button>
            ))}
          </nav>
        )}

        {categoryState.loading && <p>Cargando datos de categoría…</p>}
        {categoryState.error && (
          <p className="backend-error">
            Error al cargar la categoría: {categoryState.error}
          </p>
        )}

        {categoryState.data && (
          <>
            <section className="backend-stats">
              <Stat label="Mejor vuelta" value={categoryState.data.bests.find((item) => item.key === "lap")?.text ?? "—"} />
              <Stat label="Vueltas" value={String(categoryState.data.counts.laps)} />
              <Stat label="Coches" value={String(categoryState.data.counts.cars)} />
              <Stat label="Pilotos" value={String(categoryState.data.counts.drivers)} />
            </section>

            <section className="backend-panel">
              <div className="backend-panel-heading">
                <div>
                  <h2>Clasificación</h2>
                  <p>Mejor tiempo por coche y piloto</p>
                </div>
                <div className="backend-metric-tabs">
                  {metrics.map((item) => (
                    <button
                      key={item.id}
                      className={metric === item.id ? "active" : ""}
                      onClick={() => setMetric(item.id)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="backend-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Pos.</th>
                      <th>Coche</th>
                      <th>Equipo</th>
                      <th>Piloto</th>
                      <th>Tiempo</th>
                      <th>Dif.</th>
                      <th>Vuelta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categoryState.data.rankings[metric].map((row) => (
                      <tr key={`${row.position}-${row.car}-${row.driver}`}>
                        <td>{row.position}</td>
                        <td>#{row.car}</td>
                        <td>{row.team}</td>
                        <td>{row.driver}</td>
                        <td>{row.text}</td>
                        <td>{row.gapText}</td>
                        <td>{row.lap}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="backend-panel">
              <div className="backend-panel-heading">
                <div>
                  <h2>Ritmo por vuelta</h2>
                  <p>Vueltas marcadas como ritmo por el backend</p>
                </div>
              </div>
              <div className="backend-chart-list">
                {categoryState.data.topCars.map((car) => (
                  <div className="backend-chart-row" key={car.car}>
                    <strong>#{car.car}</strong>
                    <span>{car.team}</span>
                    <div className="backend-bars">
                      {car.laps.map((lap) => (
                        <i
                          key={lap.lap}
                          title={`Vuelta ${lap.lap}: ${formatLapTime(lap.seconds)} · ${lap.driver}`}
                          style={{
                            height: `${Math.max(
                              8,
                              Math.min(100, ((lap.seconds ?? 0) - 100) * 2),
                            )}%`,
                          }}
                        />
                      ))}
                    </div>
                    <small>{car.laps.length} vueltas</small>
                  </div>
                ))}
              </div>
            </section>

            <section className="backend-panel">
              <div className="backend-panel-heading">
                <div>
                  <h2>Detalle del coche</h2>
                  <p>Rendimiento por piloto y registro de vueltas</p>
                </div>
                <select
                  className="backend-car-select"
                  value={activeCarNumber}
                  onChange={(event) => setCarNumber(event.target.value)}
                  aria-label="Seleccionar coche"
                >
                  {cars.map((car) => (
                    <option key={car.number} value={car.number}>
                      #{car.number} · {car.team}
                    </option>
                  ))}
                </select>
              </div>

              {carState.loading && <p>Cargando coche…</p>}
              {carState.error && (
                <p className="backend-error">Error al cargar el coche: {carState.error}</p>
              )}

              {carState.data && (
                <>
                  <p className="backend-car-title">
                    #{carState.data.car.number} · {carState.data.car.team} ·{" "}
                    {carState.data.car.category}
                  </p>

                  <div className="backend-drivers">
                    {carState.data.drivers.map((driver) => (
                      <article key={driver.name}>
                        <strong>{driver.name}</strong>
                        <span>Mejor: {driver.best.text}</span>
                        <span>Mediana: {driver.median.text}</span>
                        <span>{driver.deltaText}</span>
                      </article>
                    ))}
                  </div>

                  <div className="backend-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Vuelta</th>
                          <th>Piloto</th>
                          <th>Tiempo</th>
                          <th>S1</th>
                          <th>S2</th>
                          <th>S3</th>
                          <th>Estado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {carState.data.laps.map((lap) => (
                          <tr key={`${lap.lap}-${lap.clock}`}>
                            <td>{lap.lap}</td>
                            <td>{lap.driver}</td>
                            <td>{lap.text}</td>
                            <td>{lap.s1}</td>
                            <td>{lap.s2}</td>
                            <td>{lap.s3}</td>
                            <td>{lap.status || (lap.isPace ? "Ritmo" : "—")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <article className="backend-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  )
}