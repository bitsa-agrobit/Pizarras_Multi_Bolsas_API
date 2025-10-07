// frontend/src/DashboardAgricola.jsx
import React, { useEffect, useMemo, useState } from "react";

/** === Helpers === */
const API = ""; // usar proxy Vite → /api

// Normalización de plaza con variantes y acentos (NO TOCAR: quedó OK)
const normalizePlaza = (p) => {
  if (!p) return "rosario";
  const s = ("" + p).toLowerCase();
  if (/(bah[ií]a|bah[ií]a\s+blanca|bbca|\bbb\b)/.test(s)) return "bahia";
  if (/(c[óo]rdoba|cordoba|\bcba\b|\bcor\b|\bcb\b)/.test(s)) return "cordoba";
  if (/(quequ[eé]n|\bqqn\b|\bque\b)/.test(s)) return "quequen";
  if (/(d[áa]rsena|\bdar\b)/.test(s)) return "darsena";
  if (/^loc(ales)?$/.test(s) || /mercado\s*local/.test(s)) return "locales";
  return "rosario";
};

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

const looksLikeFuturo = (name = "") =>
  /\b\d{2}\/\d{4}\b/i.test(name) ||
  /\b(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)\b/i.test(name) ||
  /(ROS|BAHIA|CHICAGO|MATBA|CBOT)/i.test(name);

/** Agrupa por producto+moneda y conserva el primero con precio numérico */
const dedupeByProducto = (items) => {
  const map = new Map();
  for (const it of items) {
    const key = `${(it.product || "").trim().toUpperCase()}|${(it.currency || "").toUpperCase()}`;
    const prev = map.get(key);
    if (!prev) map.set(key, it);
    else if (!isNumeric(prev.price) && isNumeric(it.price)) map.set(key, it);
  }
  return Array.from(map.values());
};

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
  const [infoUrl, setInfoUrl] = useState("https://www.bolsadecereales.com/camara-arbitral");
  const [loading, setLoading] = useState(false);

  const fetchData = async (pz = plaza, t = tab) => {
    setLoading(true);
    try {
      const onlyBase = t === "base" ? 1 : 0;
      const res = await fetch(
        `${API}/api/cotizaciones?plaza=${encodeURIComponent(normalizePlaza(pz))}&only_base=${onlyBase}`
      );
      const data = await res.json();

      const items = Array.isArray(data.items)
        ? data.items.map((m) => ({
            product: m.product ?? m.producto ?? m.name ?? m.nombre ?? "",
            price: m.price ?? m.precio ?? null,
            currency: (m.currency ?? m.moneda ?? "ARS")?.toUpperCase(),
            delivery: m.delivery ?? m.entrega ?? "spot",
            is_base: m.is_base ?? m.base ?? true,
          }))
        : [];

      setRows(items);
      if (data.source_url) setInfoUrl(data.source_url);
      setLastUpdated(new Date());
    } catch (e) {
      console.error(e);
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(plaza, tab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plaza, tab]);

  /** Filtrado de lista para pintar */
  const filtered = useMemo(() => {
    const base = rows.filter((r) => {
      const isFut = looksLikeFuturo(r.product);
      return tab === "base" ? !isFut : isFut;
    });
    const byCurr = base.filter((r) => (r.currency || "").toUpperCase() === currency);
    const uniq = dedupeByProducto(byCurr);
    const finalList = hideSC ? uniq.filter((r) => isNumeric(r.price)) : uniq;

    finalList.sort((a, b) => {
      const aN = isNumeric(a.price) ? 0 : 1;
      const bN = isNumeric(b.price) ? 0 : 1;
      if (aN !== bN) return aN - bN;
      return (a.product || "").localeCompare(b.product || "");
    });
    return finalList;
  }, [rows, tab, currency, hideSC]);

  /** KPIs */
  const kpi = useMemo(() => {
    const nums = filtered.map((r) => r.price).filter(isNumeric);
    const avg = nums.length > 0 ? nums.reduce((a, b) => a + b, 0) / nums.length : 0;
    return { promedio: avg, activos: nums.length };
  }, [filtered]);

  /** Acciones UI */
  const onStart = async () => {
    try {
      const res = await fetch(
        `${API}/api/start?plaza=${encodeURIComponent(normalizePlaza(plaza))}&interval_min=${intervalMin}`,
        { method: "POST" }
      );
      const js = await res.json();
      alert(js?.ok ? "Éxito: Automatización iniciada" : `Error: ${js?.message || "desconocido"}`);
    } catch {
      alert("Error de red al iniciar");
    }
  };

  const onExportOracle = async () => {
    try {
      const res = await fetch(
        `${API}/api/export/oracle?plaza=${encodeURIComponent(normalizePlaza(plaza))}`,
        { method: "POST" }
      );
      const js = await res.json();
      alert(js?.ok ? `Éxito: exportadas ${js.exported} filas` : `Error: ${js?.error || "desconocido"}`);
    } catch {
      alert("Error de red al exportar");
    }
  };

  const onDownloadCSV = async () => {
    try {
      const res = await fetch(
        `${API}/api/csv?plaza=${encodeURIComponent(normalizePlaza(plaza))}`
      );
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cotizaciones_${normalizePlaza(plaza)}.csv`;
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
            onClick={() => fetchData(plaza, tab)}
            className="mt-3 inline-flex cursor-pointer items-center rounded-xl bg-slate-900 px-4 py-2 text-white hover:bg-slate-800 active:scale-[.99]"
            title="Actualizar ahora"
          >
            Actualizar ahora
          </button>
        </div>
      </div>

      {/* Grid principal: lista + panel sticky */}
      <div className="mt-8 grid grid-cols-1 gap-6 xl:grid-cols-[1fr_380px]">
        {/* Lista */}
        <section className="rounded-2xl">
          {/* Título + controles */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <h2 className="text-xl font-semibold text-slate-900">
              Cotizaciones <span className="text-slate-500"> · {normalizePlaza(plaza)}</span>
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
                title="Ver productos base"
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
                title="Ver futuros / entregas"
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
                    title={`Mostrar ${c}`}
                  >
                    {c}
                  </button>
                ))}
              </div>

              {/* Ocultar s/c */}
              <label className="ml-2 inline-flex cursor-pointer items-center gap-2 text-sm text-slate-700" title="Ocultar precios s/c">
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

            {!loading && filtered.length === 0 && (
              <div className="rounded-xl border border-slate-200 bg-white p-4 text-slate-500">
                Sin datos
              </div>
            )}

            {filtered.map((item, idx) => {
              const hasNum = isNumeric(item.price);
              return (
                <div
                  key={`${item.product}-${item.currency}-${idx}`}
                  className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm"
                >
                  <div className="flex items-center gap-3">
                    <div className="grid h-9 w-9 place-content-center rounded-full bg-emerald-50 text-emerald-700">
                      {(item.product || "?").trim()[0] || "?"}
                    </div>
                    <div>
                      <div className="text-slate-900 font-medium">
                        {item.product || "—"}
                      </div>
                      <div className="text-xs uppercase tracking-wide text-slate-500">
                        {(item.product || "").slice(0, 4) || ""}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className={`${hasNum ? "text-slate-900 font-semibold" : "text-slate-400"}`}>
                      {hasNum ? fmtMoney(item.price, item.currency) : "s/c"}
                    </span>
                    <span className="text-[10px] rounded-md bg-slate-100 px-1.5 py-0.5 text-slate-500">
                      {(item.currency || "").toUpperCase()}
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

              {/* Contenedor alineado (quedó OK, no tocar estilos globales) */}
              <div className="flex w-full flex-wrap gap-2 rounded-xl border border-slate-200 bg-white p-1">
                {[
                  { k: "rosario", label: "Rosario" },
                  { k: "bahia", label: "Bahía Blanca" },
                  { k: "cordoba", label: "Córdoba" },
                  { k: "quequen", label: "Quequén" },
                  { k: "darsena", label: "Dársena" },
                  { k: "locales", label: "Locales" },
                ].map((p) => (
                  <button
                    key={p.k}
                    className={`cursor-pointer rounded-lg px-3 py-1.5 text-sm leading-none
                      ${normalizePlaza(plaza) === p.k
                        ? "bg-slate-900 text-white"
                        : "text-slate-700 hover:bg-slate-50"}`}
                    onClick={() => setPlaza(p.k)}
                    title={`Cambiar a ${p.label}`}
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
                title="Iniciar automatización"
              >
                Iniciar
              </button>
              <button
                onClick={onExportOracle}
                className="cursor-pointer rounded-xl bg-amber-500 px-4 py-2 text-white hover:bg-amber-600 active:scale-[.99]"
                title="Exportar a Oracle"
              >
                Exportar a Oracle
              </button>
              <button
                onClick={onDownloadCSV}
                className="cursor-pointer rounded-xl border border-slate-200 bg-white px-4 py-2 text-slate-800 hover:bg-slate-50 active:scale-[.99]"
                title="Descargar CSV"
              >
                Descargar CSV
              </button>
            </div>
          </div>
        </aside>
      </div>

      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="text-sm text-slate-600">
          Fuente:{" "}
          <a
            className="text-blue-600 hover:underline"
            href={infoUrl}
            target="_blank"
            rel="noreferrer"
          >
            Cámara Arbitral de la Bolsa
          </a>
        </div>
      </div>
    </div>
  );
}