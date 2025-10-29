# Activepieces – Flujos para API Pizarras (Sprint 1)

**Objetivo**: Automatizar dos flujos en Activepieces Cloud (plan free) sin tocar el front:
1) **Daily Refresh (06:55 ART)** – Ejecuta `/internal/refresh` para rosario, bahia_blanca y locales.
2) **Daily Mini-log (07:00 ART)** – Ejecuta `/internal/report` y envía el resumen a un webhook (Slack/Teams/Discord) o por Email.

> Zona horaria: **America/Cordoba**.  
> Requiere que la API tenga activos los endpoints internos protegidos por `X-API-Token`.

---

## 0) Prerrequisitos
- **API_BASE**: URL base de tu API (p. ej. `http://localhost:8001` o tu dominio público).
- **API_TOKEN_INTERNAL**: Token que protege los endpoints internos.
- Endpoints disponibles en tu API:
  - `POST /internal/refresh?plaza=...&only_base=1[&fecha=YYYY-MM-DD]`
  - `GET /internal/report?date=YYYY-MM-DD` (si omitís `date`, usa **hoy** por defecto).

---

## 1) Variables en Activepieces
Podés crear Variables/Connections (o setear estos valores directamente en cada paso):

- `API_BASE` = `http://TU_HOST:8001`
- `API_TOKEN_INTERNAL` = `XXXXXXXX...`
- (Opcional) `WEBHOOK_URL` = URL de Slack/Teams/Discord si vas a notificar por webhook.

---

## 2) Flow A — Daily Refresh (06:55)
**Trigger**
- **Schedule** → **Every day**
  - Hour: `06:55`
  - Timezone: **America/Cordoba**
  - Run on weekends: habilitado

**Paso 1 — Code (JS) – lista de plazas**
```javascript
export const code = async (inputs) => { 
  return [
    { plaza: 'rosario' },
    { plaza: 'bahia_blanca' },
    { plaza: 'locales' }
  ];
};
```
> El Code piece devuelve un **array** de objetos. Activepieces lo mostrará como una lista de items.

**Paso 2 — Loop / For Each**
- Iterar sobre la salida del Code (el array de plazas).

**Dentro del Loop → Paso 2.1 — HTTP Request (POST)**
- Method: **POST**
- URL: `{{API_BASE}}/internal/refresh`
- Query params:
  - `plaza` = `{{loop.item.plaza}}`
  - `only_base` = `1`
- Headers:
  - `X-API-Token` = `{{API_TOKEN_INTERNAL}}`
- Body: vacío
- Timeout: `60000 ms`
- Retries: **2** (si tu UI lo permite; si no, activá *continue on failure* y añadí un reintento manual).

**Paso 3 (opcional) — Consolidar resultados**
- Code step para armar un pequeño resumen:
```javascript
export const code = async (inputs) => { 
  const items = inputs?.loop?.items ?? [];
  return { count: items.length, results: items };
};
```

**Activar** el Flow.

---

## 3) Flow B — Daily Mini-log (07:00)
**Trigger**
- **Schedule** → **Every day**
  - Hour: `07:00`
  - Timezone: **America/Cordoba**

**Paso 1 — HTTP Request (GET)**
- URL: `{{API_BASE}}/internal/report`
- Method: **GET**
- Query params: *(opcional)* `date = YYYY-MM-DD`  
  > Si tu endpoint ya usa por defecto **hoy**, podés **omitir** `date`.
- Headers:
  - `X-API-Token` = `{{API_TOKEN_INTERNAL}}`
- Timeout: `60000 ms`
- Retries: **2**

**Paso 2 — Formatear mensaje (Code piece – JS)**
```javascript
export const code = async (inputs) => {
  const r = inputs?.http_request_1?.responseBody ?? inputs;
  const lines = [];
  lines.push(`📊 Mini-log ${r.date}`);
  for (const p of (r.plazas || [])) { 
    const status = p.ok ? 'OK' : 'ERROR';
    const t = p.duration_s ?? 0;
    lines.push(`• ${p.plaza}: ${status} – items: ${p.items} – t: ${t}s`);
  }
  return { text: lines.join('\n'), raw: r };
};
```

**Paso 3A — Enviar a Webhook (Slack/Teams/Discord)**
- HTTP Request (POST)
  - URL: `{{WEBHOOK_URL}}`
  - Headers: `Content-Type: application/json`
  - Body (JSON) según plataforma (ver ejemplos más abajo).

**(Alternativa 3B — Email)**
- Usar pieza **Email** con:
  - Subject: `Mini-log Pizarras {{today}}`
  - Body: `{{steps.code_2.text}}` (ajustá al nombre real del Code step)

**Activar** el Flow.

---

## 4) Ejemplos de payload para webhooks

### 4.1 Slack (texto simple)
```json
{ "text": "📊 Mini-log 2025-10-27\n• rosario: OK – items: 15 – t: 2.1s\n• bahia_blanca: OK – items: 12 – t: 1.8s\n• locales: ERROR – items: 0 – t: 0.5s" }
```

### 4.2 Slack (Blocks, con monoespaciado)
```json
{
  "blocks": [
    { "type": "section", "text": { "type": "mrkdwn", "text": "*📊 Mini-log 2025-10-27*" } },
    { "type": "section", "text": { "type": "mrkdwn", "text": "```rosario: OK  – items: 15 – t: 2.1s\nbahia_blanca: OK – items: 12 – t: 1.8s\nlocales: ERROR – items: 0 – t: 0.5s```" } }
  ]
}
```

### 4.3 Discord
```json
{ "content": "📊 Mini-log 2025-10-27\n• rosario: OK – items: 15 – t: 2.1s\n• bahia_blanca: OK – items: 12 – t: 1.8s\n• locales: ERROR – items: 0 – t: 0.5s" }
```

### 4.4 Microsoft Teams (conector entrante)
```json
{
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "summary": "Mini-log Pizarras",
  "themeColor": "0078D7",
  "title": "📊 Mini-log 2025-10-27",
  "text": "• rosario: OK – items: 15 – t: 2.1s\n• bahia_blanca: OK – items: 12 – t: 1.8s\n• locales: ERROR – items: 0 – t: 0.5s"
}
```

---

## 5) Pruebas rápidas
### Verificar token/Endpoints
```bash
# Sin token → 401/403
curl -i "$API_BASE/internal/refresh?plaza=rosario&only_base=1"

# Con token
curl -H "X-API-Token: $API_TOKEN_INTERNAL" "$API_BASE/internal/refresh?plaza=bahia_blanca&only_base=1"
curl -H "X-API-Token: $API_TOKEN_INTERNAL" "$API_BASE/internal/report"
```

### Ejecutar Flows manualmente
- Flow A: validá 3 ejecuciones POST (rosario/bahia_blanca/locales) con `200 OK`.
- Flow B: validá el GET y que llegue el mensaje al canal/email.

---

## 6) Operación y observabilidad
- Revisá **Runs/Executions** en Activepieces.
- Si hay 403/5xx, se verán los reintentos y el paso fallido.
- Guardá capturas/IDs de ejecución como evidencia del proyecto.

---

## 7) Roadmap (migración futura)
- **Self-host** Activepieces o **n8n** (ya tenés .json para n8n).
- Agregar colas (Redis), dead-letter y métricas.
- Capa de Agente (OpenAI) para resúmenes/backfills bajo demanda.

---
