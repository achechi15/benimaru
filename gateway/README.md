# Gateway

API **HTTP/JSON** de entrada (Go, `:8080`) que enruta hacia los servicios de backend. Dos mecanismos de enrutado:

1. **Reverse proxy genérico (data-driven):** lee `upstreams.json` y reenvía HTTP (o gRPC passthrough) sin código.
2. **Handlers a medida (`Override`):** un handler Go por servicio que **traduce HTTP/JSON ⇄ gRPC**. Lo usan `metapod`, `flowmetapod` y `profanity`.

```
        HTTP/JSON                         gRPC
Cliente ───────────► Gateway (chi, :8080) ───────────► backend (metapod / profanity / ...)
                     │  middlewares: logging, CORS, API key
                     │  routing por prefijo (Mount)
                     └─ Override.handler traduce JSON ⇄ protobuf
```

---

## Estructura

```
gateway/
├── cmd/main.go                  # entrypoint: registra Overrides y monta el router
└── internal/
    ├── config/                  # carga de config + upstreams (JSON)
    ├── gen/<svc>/v1/            # stubs gRPC Go (generados desde el .proto)
    ├── services/<svc>/          # handlers Override (HTTP ⇄ gRPC) por servicio
    ├── upstream/                # modelo Upstream (datos del upstream)
    ├── proxy/                   # reverse proxy genérico
    ├── routes/                  # Registry + router (chi)
    └── middleware/              # logging, CORS, API key, ...
```

---

## Enrutado

El router (`internal/routes`) monta cada upstream por su **`prefix`**. Para cada uno:

- Si hay un `Override` registrado con su `name` → usa ese handler a medida.
- Si no → usa el reverse proxy genérico (`internal/proxy`), configurado por los campos del upstream.

Registro de Overrides en [`cmd/main.go`](cmd/main.go):

```go
reg.Override("metapod", metapod.Builder)
reg.Override("profanity", profanity.Builder)
reg.Override("flowmetapod", flowmetapod.Builder)
```

Middlewares: `Logging` y `CORS` son globales; `APIKey` se aplica por servicio si `GATEWAY_API_KEY` está definido (hoy a `metapod` y `profanity`).

---

## Upstreams

Definidos en JSON, vía `GATEWAY_UPSTREAMS_FILE` (ruta a fichero) o `GATEWAY_UPSTREAMS` (inline, usado por Docker). Ejemplo:

```json
[
  { "name": "metapod",     "prefix": "/v1/metapod",   "target": "localhost:50051" },
  { "name": "flowmetapod", "prefix": "/flow/metapod", "target": "localhost:50051" },
  { "name": "profanity",   "prefix": "/v1/profanity", "target": "localhost:50052" }
]
```

| Campo | Descripción |
|---|---|
| `name` | Clave del servicio; enlaza con middlewares y con el `Override` |
| `prefix` | Prefijo de ruta HTTP montado |
| `target` | Backend. En servicios `Override` es la **dirección gRPC** (`host:port`, sin esquema) |
| `protocol`, `stripPrefix`, `stream`, `timeout` | Solo aplican al **proxy genérico**; con `Override` se ignoran |

---

## Endpoints

### `POST /v1/metapod` — job asíncrono (metapod)

```bash
curl -i -X POST localhost:8080/v1/metapod \
  -H 'content-type: application/json' \
  -d '{"brand":"acme","channel":"web","id":"123","prompt":"hola"}'
```

Responde `202 {"status":"accepted","id":"123"}`; el resultado llega luego por callback.

### `POST /v1/profanity` — análisis de texto o imagen

El handler ([`internal/services/profanity/handler.go`](internal/services/profanity/handler.go)) decide la rama según los campos presentes en el cuerpo:

- Solo **`text`** → `AnalyzeText`. Respuesta: mapa de probabilidades.
- Solo **`url`** → `AnalyzeImage` (Gemini). Respuesta: `{"profanity_check": bool}`.
- **Ambos** → se analizan **en paralelo** y la respuesta los combina en `{"text": ..., "image": ...}`.

**Texto:**

```bash
curl -s -X POST localhost:8080/v1/profanity \
  -H 'content-type: application/json' \
  -d '{"text":"eres un idiota"}'
# -> {"NEG":0.91,"NEU":0.07,"POS":0.02}
```

**Imagen:**

```bash
curl -s -X POST localhost:8080/v1/profanity \
  -H 'content-type: application/json' \
  -d '{"url":"https://mi-bucket.s3.amazonaws.com/img/123.jpg"}'
# -> {"profanity_check":true}
```

**Texto + imagen:**

```bash
curl -s -X POST localhost:8080/v1/profanity \
  -H 'content-type: application/json' \
  -d '{"text":"eres un idiota","url":"https://mi-bucket.s3.amazonaws.com/img/123.jpg"}'
# -> {"text":{"NEG":0.91,"NEU":0.07,"POS":0.02},"image":{"profanity_check":true}}
```

| Cuerpo | Rama | gRPC | Respuesta |
|---|---|---|---|
| `{"text":"..."}` | texto | `AnalyzeText` | `{ "<label>": <proba>, ... }` |
| `{"url":"..."}` | imagen | `AnalyzeImage` | `{"profanity_check": bool}` |
| `{"text":"...","url":"..."}` | ambos (paralelo) | `AnalyzeText` + `AnalyzeImage` | `{"text": {...}, "image": {"profanity_check": bool}}` |

Solo se acepta **POST**; otro método → `405`. JSON inválido → `400`. Falta `text` y `url` → `400`. Error del backend gRPC → `502`.

### `GET /healthz`

```bash
curl localhost:8080/healthz   # -> ok (200)
```

---

## Caché y deduplicación (profanity)

El handler de profanity usa **Valkey** (si `VALKEY_SERVER_URL` está definido) como caché best-effort con TTL de 24 h:

- Texto: clave = el propio texto.
- Imagen: clave = `img:<url>`.

Si Valkey no está disponible, el handler funciona igual sin caché. Además usa **singleflight**: peticiones idénticas concurrentes se resuelven una sola vez (clave texto, o `img:<url>` en imagen).

---

## Configuración

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `GATEWAY_ADDR` | no | `:8080` | Dirección de escucha |
| `GATEWAY_UPSTREAMS_FILE` | sí* | — | Ruta al JSON de upstreams |
| `GATEWAY_UPSTREAMS` | sí* | — | JSON de upstreams inline (Docker) |
| `GATEWAY_PROXY_TIMEOUT` | no | `10s` | Timeout del proxy genérico (no aplica a Overrides) |
| `GATEWAY_API_KEY` | no | — | Si se define, exige `X-API-Key` en metapod y profanity |
| `GATEWAY_ALLOWED_ORIGINS` | no | — | Orígenes CORS |
| `VALKEY_SERVER_URL` | no | — | Habilita la caché de profanity (`host:port`) |

\* Obligatoria una de `GATEWAY_UPSTREAMS_FILE` o `GATEWAY_UPSTREAMS`. En local se carga `.env` con `godotenv`, así que ejecuta el gateway desde `gateway/`.

---

## Ejecutar

```bash
cd gateway
go run ./cmd        # HTTP en :8080
```

O con Docker Compose desde la raíz (`docker compose up --build`).

---

## Añadir un servicio gRPC con fachada HTTP (Override)

1. Define el RPC en el `.proto` y regenera stubs: `cd api && buf generate`.
2. Crea `internal/services/<nombre>/handler.go` con un `Builder` que abra el cliente gRPC y traduzca JSON ⇄ protobuf.
3. Regístralo en `cmd/main.go`: `reg.Override("<nombre>", <nombre>.Builder)`.
4. Añade su entrada en `upstreams.json` (`target` = dirección gRPC).

Para un servicio puramente HTTP basta con añadir la entrada en `upstreams.json` (sin código).
