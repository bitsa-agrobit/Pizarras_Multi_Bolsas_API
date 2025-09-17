import React, { useEffect, useMemo, useState } from "react";

// --- Utilidades de formato ---
const fmtNumber = (n) => new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 }).format(n ?? 0);
const fmtUSD = (n) => `$${fmtNumber(n)}`;

// --- Badges de variación ---
function ChangeBadge({ value }) {
  const isUp = value >= 0;
  return (
    <span className={`text-xs px-2 py-1 rounded-md inline-flex items-center gap-1 ${
      isUp ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
    }`}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {isUp ? (
          <polyline points="18 15 12 9 6 15" />
        ) : (
          <polyline points="6 9 12 15 18 9" />
        )}
      </svg>
      {fmtNumber(Math.abs(value))}
    </span>
  );
}

// --- Tarjeta KPI ---
function KpiCard({ title, value, deltaLabel }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 flex flex-col gap-2">
      <div className="text-gray-500 text-sm">{title}</div>
      <div className="text-2xl font-semibold">{value}</div>
      {deltaLabel ? (
        <div className="text-xs text-gray-400">{deltaLabel}</div>
      ) : null}
    </div>
  );
}

// --- Ítem de lista de producto ---
function ProductRow({ code, name, price, change, updatedAt }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 px-4 py-3 flex items-center justify-between hover:shadow-sm transition">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
          {code?.slice(0,1) || "?"}
        </div>
        <div>
          <div className="font-medium text-gray-800">{name}</div>
          <div className="text-xs text-gray-400">{code}</div>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="font-semibold">{fmtUSD(price)}</div>
          <div className="text-[11px] text-gray-400">Últ. act: {updatedAt}</div>
        </div>
        <ChangeBadge value={change} />
      </div>
    </div>
  );
}

// --- Panel de configuración ---
function ScrapingConfig({ url, intervalMin, active, onChange, onRun, onExport, onCSV }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-5 flex flex-col gap-4">
      <div>
        <div className="font-semibold text-gray-800">Configuración de Web Scraping</div>
        <div className="text-sm text-gray-500">Automatización de recopilación de cotizaciones</div>
      </div>

      <label className="text-sm text-gray-600">URL de la Bolsa de Cereales</label>
      <input
        className="border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-300"
        value={url}
        onChange={(e) => onChange({ url: e.target.value })}
        placeholder="https://…"
      />

      <label className="text-sm text-gray-600">Intervalo de actualización (minutos)</label>
      <input
        type="number"
        className="border rounded-lg px-3 py-2 w-24 focus:outline-none focus:ring-2 focus:ring-emerald-300"
        value={intervalMin}
        onChange={(e) => onChange({ intervalMin: Number(e.target.value) })}
      />

      <div className="flex items-center gap-3">
        <span className={`text-xs px-2 py-1 rounded-md ${active ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>
          {active ? "Activo" : "Inactivo"}
        </span>
      </div>

      <div className="flex flex-wrap gap-3 pt-1">
        <button onClick={onRun} className="px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700">
          Iniciar Scraping
        </button>
        <button onClick={onExport} className="px-4 py-2 rounded-lg bg-amber-500 text-white hover:bg-amber-600">
          Exportar a Oracle
        </button>
        <button onClick={onCSV} className="px-4 py-2 rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200">
          Descargar CSV
        </button>
      </div>
    </div>
  );
}

// --- Componente principal ---
export default function DashboardAgricola() {
  // Estado local con datos simulados (reemplazar por fetch a tu API FastAPI)
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState([
    { code: "TPAN", name: "Trigo Pan", price: 274.39, change: -5.04, updatedAt: "03:38 p. m." },
    { code: "MAIZ", name: "Maíz",      price: 192.42, change:  2.85, updatedAt: "03:38 p. m." },
    { code: "SOJA", name: "Soja",      price: 427.95, change:  3.80, updatedAt: "03:38 p. m." },
    { code: "GIRA", name: "Girasol",   price: 514.06, change:  1.06, updatedAt: "03:38 p. m." },
  ]);

  const kpis = useMemo(() => ({
    volumen: 12845,
    promedio: 355.62,
    activos: 24,
    ultima: "Tiempo real",
  }), []);

  const [cfg, setCfg] = useState({
    url: "https://www.bolsadecereales.com/cotizaciones",
    intervalMin: 5,
    active: false,
  });

  // Ejemplo de carga desde API
  async function fetchQuotes() {
    setLoading(true);
    try {
      // Descomentar y ajustar endpoint cuando tengas el JSON del backend
      // const res = await fetch("/api/cotizaciones?fuente=bdec_bsas");
      // const json = await res.json();
      // setData(json.items);
      await new Promise((r) => setTimeout(r, 800)); // simulación
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchQuotes();
  }, []);

  return (
    <div className="min-h-screen bg-[#F6F7F9]">
      {/* Header */}
      <header className="bg-white border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-5 py-4">
          <h1 className="text-2xl font-bold text-gray-900">Sistema de Cotizaciones Agrícolas</h1>
          <div className="text-sm text-emerald-700">Monitoreo en tiempo real • Integración Oracle • Automatización completa</div>
        </div>
      </header>

      {/* Contenido */}
      <main className="max-w-6xl mx-auto px-5 py-6 flex flex-col gap-6">
        {/* KPIs */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard title="Volumen Total" value={`${fmtNumber(kpis.volumen)} Tn`} deltaLabel="+8.5%" />
          <KpiCard title="Precio Promedio" value={fmtUSD(kpis.promedio)} deltaLabel="+2.1%" />
          <KpiCard title="Cereales Activos" value={kpis.activos} deltaLabel="0%" />
          <KpiCard title="Última Actualización" value="15:32" deltaLabel={kpis.ultima} />
        </section>

        {/* Listado de cotizaciones */}
        <section className="bg-white rounded-2xl border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="font-semibold text-gray-800">Cotizaciones de Cereales</div>
              <div className="text-sm text-gray-500">Mercado de Buenos Aires · Tiempo real</div>
            </div>
            <button
              onClick={fetchQuotes}
              disabled={loading}
              className="px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {loading ? "Actualizando…" : "Actualizar"}
            </button>
          </div>

          <div className="grid gap-3">
            {data.map((row) => (
              <ProductRow key={row.code} {...row} />
            ))}
          </div>
        </section>

        {/* Configuración */}
        <ScrapingConfig
          url={cfg.url}
          intervalMin={cfg.intervalMin}
          active={cfg.active}
          onChange={(patch) => setCfg((s) => ({ ...s, ...patch }))}
          onRun={() => alert("Iniciar scraping (llamar endpoint /api/scrape)")}
          onExport={() => alert("Exportar a Oracle (POST /api/export/oracle)")}
          onCSV={() => alert("Descargar CSV (GET /api/csv)")}
        />
      </main>
    </div>
  );
}