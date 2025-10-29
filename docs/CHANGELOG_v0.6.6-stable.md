# CHANGELOG v0.6.6-stable

## Cambios
- Endpoint público `/api/cotizaciones` con cache TTL 120s.
- Fallback opcional Playwright (modo async) detrás de `USE_PLAYWRIGHT=1`.
- Headers “browser-like” + intento HTTP/2 con httpx.

## Fixes
- Manejo robusto de 403 (Cloudflare) y timeouts.
- Export ORACLE idempotente por `UVALUE` (MERGE).
- Normalización de plazas y filtrado `only_base=1`.

## Notas operativas
- Requiere `.env` sin secretos en repo.
- Front consume `/api/cotizaciones?plaza=Rosario&only_base=1`.
- Bundle “airbag” adjunto al release.

## Verificaciones
- `/api/health` OK
- `/api/cotizaciones?plaza=Rosario&only_base=1` OK (cached true/false)
- Fallback: no usado en flujo normal
- Export Oracle: probado manual (entorno TEST_EMAN)
