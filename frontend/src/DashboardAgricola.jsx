import React, { useEffect, useMemo, useState } from "react";

// --- Utils ---
const fmtNumber = (n) => new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 }).format(n ?? 0);
// antes:
// const fmtUSD = (n) => `$${fmtNumber(n)}`;

// después (reemplazá esa línea por esta):
const fmtUSD = (n, c) =>
  n == null
    ? 's/c'
    : new Intl.NumberFormat('es-AR', {
      style: 'currency',
      currency: c || 'USD',
      maximumFractionDigits: 2,
    }).format(n);

const fmtMoney = fmtUSD; // alias para compatibilidad

function ChangeBadge({ value }) {
  const isUp = value >= 0;
  return (
    <span
      className={`text-xs px-2 py-1 rounded-md inline-flex items-center gap-1 ${isUp ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
        }`}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {isUp ? <polyline points="18 15 12 9 6 15" /> : <polyline points="6 9 12 15 18 9" />}
      </svg>
      {fmtNumber(Math.abs(value))}
    </span>
  );
}

function KpiCard({ title, value }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 flex flex-col gap-2">
      <div className="text-gray-500 text-sm">{title}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}

function ProductRow({ code, name, price, currency, change, updatedAt }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 px-4 py-3 flex items-center justify-between hover:shadow-sm transition">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
          {code?.slice(0, 1) || "?"}
        </div>
        <div>
          <div className="font-medium text-gray-800">{name}</div>
          <div className="text-xs text-gray-400">{code}</div>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="font-semibold flex items-center gap-2">
            <span>{fmtUSD(price, currency)}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">{currency}</span>
          </div>
          <div className="text-[11px] text-gray-400">Últ. act: {updatedAt}</div>
        </div>
        <ChangeBadge value={change} />
      </div>
    </div>
  );
}

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
      />

      <label className="text-sm text-gray-600">Intervalo de actualización (minutos)</label>
      <input
        type="number"
        className="border rounded-lg px-3 py-2 w-24 focus:outline-none focus:ring-2 focus:ring-emerald-300"
        value={intervalMin}
        onChange={(e) => onChange({ intervalMin: Number(e.target.value) })}
      />

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

export default function DashboardAgricola() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState([]);
  const [errorMsg, setErrorMsg] = useState("");

  const kpis = useMemo(() => ({
    volumen: 12845,
    promedio: 355.62,
    activos: 24,
    ultima: "Tiempo real",
  }), []);

  const [cfg, setCfg] = useState({
    url: "https://www.bolsadecereales.com/camara-arbitral",
    intervalMin: 5,
    active: false,
  });

  async function fetchQuotes() {
    setLoading(true);
    setErrorMsg("");
    try {
      const res = await fetch('/api/cotizaciones');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData((json.items || []).map((r) => ({
        code: (r.producto || "").slice(0, 4).toUpperCase(),
        name: r.producto,
        price: r.precio,
        currency: (r.moneda || 'USD').toUpperCase(),  // <-- usar la moneda del backend
        change: 0,
        updatedAt: r.fecha,
      })));
    } catch (e) {
      setErrorMsg(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchQuotes();                           // primera carga
    const id = setInterval(fetchQuotes, cfg.intervalMin * 60 * 1000);
    return () => clearInterval(id);
  }, [cfg.intervalMin]);

  return (
    <div className="min-h-screen bg-[#F6F7F9] p-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <KpiCard title="Volumen (tn)" value={fmtNumber(kpis.volumen)} />
        <KpiCard title="Precio Promedio" value={fmtUSD(kpis.promedio)} />
        <KpiCard title="Activos" value={kpis.activos} />
        <KpiCard title="Última actualización" value={kpis.ultima} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2 flex flex-col gap-3">
          <div className="font-semibold text-gray-700">Cotizaciones</div>

          {errorMsg && (
            <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm">Error: {errorMsg}</div>
          )}

          {loading ? (
            <div className="text-sm text-gray-500">Cargando…</div>
          ) : data.length === 0 ? (
            <div className="text-sm text-gray-500">Sin datos</div>
          ) : (
            data.map((p, i) => <ProductRow key={i} {...p} />)
          )}
        </div>

        <ScrapingConfig
          url={cfg.url}
          intervalMin={cfg.intervalMin}
          active={cfg.active}
          onChange={(patch) => setCfg((s) => ({ ...s, ...patch }))}
          onRun={async () => {
            await fetch("/api/scrape", { method: "POST" });
            await fetchQuotes();
          }}
          onExport={async () => {
            await fetch("/api/export/oracle", { method: "POST" });
            alert("Exportación a Oracle solicitada.");
          }}
          onCSV={() => window.open("/api/csv?sc=blank", "_blank")}
        />
      </div>
    </div>
  );
}