// frontend/src/DashboardAgricola.jsx
import React, { useEffect, useMemo, useState } from "react";

/** === Helpers === */

// Autodetección del backend:
// - Usa VITE_API_BASE si está seteada (ej: http://localhost:8001)
// - Si estamos en localhost y no hay env, intenta http://localhost:8001
// - Luego, si algo de eso falla en runtime, hacemos fallback a ruta relativa (/api)
function getApiBase() {
  const env = import.meta?.env?.VITE_API_BASE;
  if (env && typeof env === "string") return env.replace(/\/+$/, "");
  const host = typeof window !== "undefined" ? window.location.hostname : "";
  if (host === "localhost" || host === "127.0.0.1") return "http://localhost:8001";
  return ""; // mismo origen (prod)
}
const API_BASE = getApiBase();

// Hace fetch JSON con fallback: primero absoluto (API_BASE), si falla → relativo (/api)
async function fetchJsonWithFallback(path, options) {
  const tryAbs = async () => {
    if (!API_BASE) throw new Error("skip-abs");
    const res = await fetch(`${API_BASE}${path}`, options);
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status} ${res.statusText} body=${body.slice(0, 300)}`);
    }
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/json")) {
      const t = await res.text();
      throw new Error(`Respuesta no JSON del backend (abs). Inicio: ${t.slice(0, 300)}`);
    }
    return res.json();
  };

  const tryRel = async () => {
    const res = await fetch(path, options);
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status} ${res.statusText} (rel) body=${body.slice(0, 300)}`);
    }
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/json")) {
      const t = await res.text();
      throw new Error(`Respuesta no JSON del backend (rel). Inicio: ${t.slice(0, 300)}`);
    }
    return res.json();
  };

  try {
    return await tryAbs();
  } catch (e) {
    // Si fue error de red (connection refused / TypeError) o forzamos skip-abs → intentamos relativo
    console.warn("[fetchJsonWithFallback] abs falló, probando relativo:", e?.message || e);
    return await tryRel();
  }
}

// Descarga binaria con fallback (para CSV)
async function fetchBlobWithFallback(path, options) {
  const tryAbs = async () => {
    if (!API_BASE) throw new Error("skip-abs");
    const res = await fetch(`${API_BASE}${path}`, options);
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status} ${res.statusText} body=${body.slice(0, 300)}`);
    }
    return res.blob();
  };
  const tryRel = async () => {
    const res = await fetch(path, options);
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status} ${res.statusText} (rel) body=${body.slice(0, 300)}`);
    }
    return res.blob();
  };
  try {
    return await tryAbs();
  } catch (e) {
    console.warn("[fetchBlobWithFallback] abs falló, probando relativo:", e?.message || e);
    return await tryRel();
  }
}

const fmtMoney = (value, currency) => {
  if (value == null || Number.isNaN(value)) return "s/c";
  const nf = new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: currency === "USD" ? "USD" : "ARS",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
  return nf.format(value);
};

const isNumeric = (v) => typeof v === "number" && Number.isFinite(v);

const looksLikeFuturo = (name = "") => {
  return (
    /\b\d{2}\/\d{4}\b/i.test(name) ||
    /\b(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)\b/i.test(name) ||
    /(ROS|BAHIA|CHICAGO|MATBA|CBOT)/i.test(name)
  );
};

/** Agrupa por producto manteniendo un único precio por moneda */
const dedupeByProducto = (items) => {
  const map = new Map();
  for (const it of items) {
    const key = `${(it.producto || "").trim().toUpperCase()}|${it.moneda}`;
    const prev = map.get(key);
    if (!prev) map.set(key, it);
    else if (!isNumeric(prev.precio) && isNumeric(it.precio)) map.set(key, it);
  }
  return Array.from(map.values());
};

/** === Componente principal === */
export default function DashboardAgricola() {
  // Filtros/estado
  const [plaza, setPlaza] = useState("rosario");
  const [tab, setTab] = useState("base"); // 'base' | 'futuros'
  const [currency, setCurrency] = useState("ARS"); // 'ARS' | 'USD'
  const [hideSC, setHideSC] = useState(true);

  // Datos
  const [rows, setRows] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [intervalMin, setIntervalMin] = useState(1440);
  const [infoUrl, setInfoUrl] = useState(
    "https://www.bolsadecereales.com/camara-arbitral"
  );
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const fetchData = async (pz = plaza) => {
    setLoading(true);
    setErrorMsg("");
    try {
      // Pedimos solo productos base y permitimos fallback a cache.
      const path = `/api/cotizaciones?plaza=${encodeURIComponent(
        pz
      )}&only_base=1&fallback_cache=1&debug=0`;

      const data = await fetchJsonWithFallback(path, { credentials: "omit" });

      setRows(Array.isArray(data.items) ? data.items : []);
      if (data.source_url) setInfoUrl(data.source_url);
      setLastUpdated(new Date());
    } catch (e) {
      console.error("fetchData error:", e);
      setRows([]);
      setErrorMsg(
        e?.message ||
          "No se pudieron obtener datos. Revisá que la API esté corriendo y el puerto sea accesible."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(plaza);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plaza]);

  /** Filtrado de lista para pintar */
  const filtered = useMemo(() => {
    const base = rows.filter((r) => {
      const isFut = looksLikeFuturo(r.producto);
      return tab === "base" ? !isFut : isFut;
    });
    const byCurr = base.filter((r) => (r.moneda || "").toUpperCase() === currency);
    const uniq = dedupeByProducto(byCurr);
    const finalList = hideSC ? uniq.filter((r) => isNumeric(r.precio)) : uniq;
    finalList.sort((a, b) => {
      const aN = isNumeric(a.precio) ? 0 : 1;
      const bN = isNumeric(b.precio) ? 0 : 1;
      if (aN !== bN) return aN - bN;
      return (a.producto || "").localeCompare(b.producto || "");
    });
    return finalList;
  }, [rows, tab, currency, hideSC]);

  /** KPIs */
  const kpi = useMemo(() => {
    const nums = filtered.map((r) => r.precio).filter(isNumeric);
    const avg =
      nums.length > 0
        ? nums.reduce((a, b) => a + b, 0) / Math.max(nums.length, 1)
        : 0;
    return {
      promedio: avg,
      activos: nums.length,
    };
  }, [filtered]);

  /** Acciones UI */
  const onStart = async () => {
    try {
      const path = `/api/start?plaza=${plaza}&interval_min=${intervalMin}`;
      const data = await fetchJsonWithFallback(path, { method: "POST" });
      alert(data?.ok ? "Éxito: Automatización iniciada" : `Error al iniciar: ${data?.message || "desconocido"}`);
    } catch {
      alert("Error de red al iniciar");
    }
  };

  const onExportOracle = async () => {
    try {
      const path = `/api/export/oracle?plaza=${plaza}&only_base=1`;
      const data = await fetchJsonWithFallback(path, { method: "POST" });
      alert(
        data?.ok
          ? `Éxito: exportadas ${data.exported} filas`
          : `Error al exportar: ${data?.error || "desconocido"}`
      );
    } catch {
      alert("Error de red al exportar");
    }
  };

  const onDownloadCSV = async () => {
    try {
      const path = `/api/csv?plaza=${plaza}&only_base=1&fallback_cache=1`;
      const blob = await fetchBlobWithFallback(path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cotizaciones_${plaza}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      alert("No se pudo descargar el CSV");
    }
  };

  const avgLabel = fmtMoney(kpi.promedio, currency);
  const lastLabel =
    lastUpdated == null
      ? "—"
      : new Intl.DateTimeFormat("es-AR", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }).format(lastUpdated);

  /** === Render === */
  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      {/* KPIs */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="text-slate-500 text-sm">Precio Promedio</div>
          <div className="mt-3 text-3xl font-semibold text-slate-900">
            {avgLabel}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="text-slate-500 text-sm">Activos</div>
          <div className="mt-3 text-3xl font-semibold text-slate-900">
            {kpi.activos}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="text-slate-500 text-sm">Última actualización</div>
          <div className="mt-1 text-lg font-medium text-slate-900">
            {lastLabel} {lastUpdated ? "· hace 0s" : ""}
          </div>
          <button
            onClick={() => fetchData(plaza)}
            className="mt-3 inline-flex cursor-pointer items-center rounded-xl bg-slate-900 px-4 py-2 text-white hover:bg-slate-800 active:scale-[.99]"
          >
            Actualizar ahora
          </button>
        </div>
      </div>

      {/* Mensaje de error visible si algo falla */}
      {errorMsg && (
        <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {errorMsg}
        </div>
      )}

      {/* Grid principal: lista + panel sticky */}
      <div className="mt-8 grid grid-cols-1 gap-6 xl:grid-cols-[1fr_380px]">
        {/* Lista */}
        <section className="rounded-2xl">
          {/* Título + controles */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <h2 className="text-xl font-semibold text-slate-900">
              Cotizaciones
              <span className="text-slate-500"> · {plaza}</span>
            </h2>

            {/* Tabs base/futuros */}
            <div className="ml-auto flex items-center gap-2">
              <button
                className={`cursor-pointer rounded-xl border px-3 py-1.5 text-sm ${
                  tab === "base"
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                }`}
                onClick={() => setTab("base")}
              >
                Productos base
              </button>
              <button
                className={`cursor-pointer rounded-xl border px-3 py-1.5 text-sm ${
                  tab === "futuros"
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                }`}
                onClick={() => setTab("futuros")}
              >
                Futuros / entregas
              </button>

              {/* Currency toggle */}
              <div className="ml-2 inline-flex rounded-xl border border-slate-200 bg-white p-0.5">
                {["ARS", "USD"].map((c) => (
                  <button
                    key={c}
                    className={`cursor-pointer rounded-lg px-3 py-1.5 text-sm ${
                      currency === c
                        ? "bg-slate-900 text-white"
                        : "text-slate-700 hover:bg-slate-50"
                    }`}
                    onClick={() => setCurrency(c)}
                  >
                    {c}
                  </button>
                ))}
              </div>

              {/* Ocultar s/c */}
              <label className="ml-2 inline-flex cursor-pointer items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 cursor-pointer accent-slate-900"
                  checked={hideSC}
                  onChange={(e) => setHideSC(e.target.checked)}
                />
                Ocultar s/c
              </label>
            </div>
          </div>

          {/* Lista de cards */}
          <div className="space-y-3">
            {loading && (
              <div className="rounded-xl border border-slate-200 bg-white p-4 text-slate-500">
                Cargando…
              </div>
            )}

            {!loading && filtered.length === 0 && !errorMsg && (
              <div className="rounded-xl border border-slate-200 bg-white p-4 text-slate-500">
                Sin datos
              </div>
            )}

            {filtered.map((item, idx) => {
              const isNum = isNumeric(item.precio);
              return (
                <div
                  key={`${item.producto}-${item.moneda}-${idx}`}
                  className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm"
                >
                  <div className="flex items-center gap-3">
                    <div className="grid h-9 w-9 place-content-center rounded-full bg-emerald-50 text-emerald-700">
                      {(item.producto || "?").trim()[0] || "?"}
                    </div>
                    <div>
                      <div className="text-slate-900 font-medium">
                        {item.producto || "—"}
                      </div>
                      <div className="text-xs uppercase tracking-wide text-slate-500">
                        {(item.producto || "").slice(0, 4) || ""}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span
                      className={`${
                        isNum ? "text-slate-900 font-semibold" : "text-slate-400"
                      }`}
                    >
                      {isNum ? fmtMoney(item.precio, item.moneda) : "s/c"}
                    </span>
                    <span className="text-[10px] rounded-md bg-slate-100 px-1.5 py-0.5 text-slate-500">
                      {(item.moneda || "").toUpperCase()}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Panel sticky de configuración */}
        <aside className="xl:sticky xl:top-6 xl:self-start">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="mb-2 text-lg font-semibold text-slate-900">
              Configuración de Web Scraping
            </h3>
            <p className="mb-4 text-sm text-slate-500">
              Automatización de recopilación de cotizaciones
            </p>

            {/* Plaza */}
            <div className="mb-4">
              <div className="mb-1 text-sm text-slate-600">Plaza</div>
              <div className="inline-flex rounded-xl border border-slate-200 bg-white p-0.5">
                {[
                  { k: "rosario", label: "Rosario" },
                  { k: "bahia", label: "Bahía Blanca" },
                  { k: "locales", label: "Locales" },
                ].map((p) => (
                  <button
                    key={p.k}
                    className={`cursor-pointer rounded-lg px-3 py-1.5 text-sm ${
                      plaza === p.k
                        ? "bg-slate-900 text-white"
                        : "text-slate-700 hover:bg-slate-50"
                    }`}
                    onClick={() => setPlaza(p.k)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {/* URL informativa */}
            <div className="mb-4">
              <div className="mb-1 text-sm text-slate-600">
                URL de la Bolsa de Cereales (informativa)
              </div>
              <input
                value={infoUrl}
                readOnly
                className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700"
              />
              <div className="mt-1 text-xs text-slate-500">
                Se sincroniza automáticamente al cambiar la plaza.
              </div>
            </div>

            {/* Intervalo */}
            <div className="mb-4">
              <div className="mb-1 text-sm text-slate-600">
                Intervalo de actualización (minutos)
              </div>
              <input
                type="number"
                min={1}
                value={intervalMin}
                onChange={(e) => setIntervalMin(Number(e.target.value) || 1)}
                className="w-40 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
              />
            </div>

            {/* Botones */}
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={onStart}
                className="cursor-pointer rounded-xl bg-emerald-600 px-4 py-2 text-white hover:bg-emerald-700 active:scale-[.99]"
              >
                Iniciar
              </button>
              <button
                onClick={onExportOracle}
                className="cursor-pointer rounded-xl bg-amber-500 px-4 py-2 text-white hover:bg-amber-600 active:scale-[.99]"
              >
                Exportar a Oracle
              </button>
              <button
                onClick={onDownloadCSV}
                className="cursor-pointer rounded-xl border border-slate-200 bg-white px-4 py-2 text-slate-800 hover:bg-slate-50 active:scale-[.99]"
              >
                Descargar CSV
              </button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}