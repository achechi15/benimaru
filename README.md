# Benimaru

Plataforma de microservicios para orquestar generación con LLM. Un **gateway** en Go expone una API **HTTP/JSON** al exterior y **traduce internamente a gRPC** hacia los servicios de backend. **metapod** (Python) recibe la petición, responde al instante y genera el flujo en segundo plano contra un modelo servido por `llama-server`; al terminar, notifica el resultado por un callback.

---

## Arquitectura

```
        HTTP/JSON                    gRPC                         HTTP
Cliente ───────────────► Gateway ───────────────► metapod ───────────────► llama-server
(front/back)             (Go, :8080)              (Python, :50051)         (:8081, interno)
  POST /v1/metapod │  traduce HTTP ⇄ gRPC              │
                   │  ◄── 202 {status,id} ─────────────┘  responde al instante (ack)
                   │
                   │      ... en segundo plano ...
                   │              metapod ──HTTP──► llama-server (genera)
                   │              metapod ──POST──► CALLBACK_URL {brand,channel,id,body,ok}
```

### Componentes

| Componente | Lenguaje | Rol |
|---|---|---|
| **gateway** | Go | Expone HTTP. Dos mecanismos de enrutado: (1) **reverse proxy genérico data-driven** que lee `upstreams.json`; (2) **handlers a medida por servicio** (`Override`) que traducen HTTP/JSON ⇄ gRPC. metapod usa el segundo. Aplica middlewares (logging, API key). |
| **metapod** | Python (grpc.aio) | Servidor gRPC. Recibe `Create`, responde al instante con un *ack* (patrón job asíncrono) y genera el flujo contra `llama-server` en background. Al terminar hace POST al callback. |
| **llama-server** | llama.cpp | Inferencia del modelo. Solo HTTP. **No se expone fuera**: solo metapod le habla. |
| **profanity** | Go | Servicio con caché Valkey. *(Incompleto — ver Estado.)* |

### Principio de diseño

- Para servicios **HTTP**, el gateway es **data-driven**: añadir uno es una entrada en `upstreams.json`, sin tocar Go.
- Para servicios **gRPC con fachada HTTP** (como metapod), se usa un **`Override`**: un handler Go por servicio que traduce JSON ⇄ protobuf. La traducción necesita conocer el `.proto`, por eso es código (no automático).

---

## Estructura del repositorio

```
Benimaru/
├── go.work                      # workspace Go: gateway + profanity
├── docker-compose.yml
├── api/
│   ├── buf.yaml · buf.gen.yaml  # generación de stubs desde el .proto
│   └── proto/metapod/v1/metapod.proto
├── gateway/                     # Go
│   ├── Dockerfile · .env
│   ├── cmd/main.go              # entrypoint
│   └── internal/
│       ├── config/              # carga de config + upstreams.json
│       ├── gen/metapod/v1/      # stubs gRPC Go (generados desde el .proto)
│       ├── services/metapod/    # handler Override: HTTP ⇄ gRPC
│       ├── upstream/            # modelo Upstream (datos)
│       ├── proxy/               # reverse proxy genérico (HTTP / gRPC passthrough)
│       ├── routes/              # Registry + router (chi)
│       └── middleware/          # logging, api-key, ...
└── services/
    ├── metapod/                 # Python (servidor gRPC)
    │   ├── Dockerfile · .env · requirements.txt
    │   ├── metapod/v1/          # stubs gRPC Python (generados, no editar)
    │   └── app/
    │       ├── server.py        # servidor gRPC (Create)
    │       ├── flow.py          # generación (llama-server) + callback
    │       └── config.py        # settings desde .env
    └── profanity/               # Go — caché Valkey (incompleto)
```

> Los stubs Go viven **dentro** del módulo del gateway (`internal/gen`), por eso no hace falta un módulo `api` separado. El `.proto` es la única fuente de verdad; de él se generan los stubs de Go (gateway) y de Python (metapod).

---

## Requisitos previos

- **Go** 1.26+
- **Python** 3.10+
- **llama-server** ([llama.cpp](https://github.com/ggml-org/llama.cpp)) y un modelo `.gguf`
- **buf** (para regenerar stubs si cambias el `.proto`)
- **curl** para probar
- **Docker + Docker Compose** (opcional)

---

## Configuración

### Gateway

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `GATEWAY_ADDR` | no | `:8080` | Dirección de escucha |
| `GATEWAY_UPSTREAMS_FILE` | **sí*** | — | Ruta al JSON de upstreams (relativa al CWD) |
| `GATEWAY_UPSTREAMS` | alternativa | — | JSON de upstreams inline (lo usa Docker) |
| `GATEWAY_PROXY_TIMEOUT` | no | `10s` | Timeout del proxy genérico (no aplica a metapod/Override) |
| `GATEWAY_API_KEY` | no | — | Si se define, exige cabecera `X-API-Key` en metapod |
| `GATEWAY_ALLOWED_ORIGINS` | no | — | Orígenes CORS (cargado, aún sin aplicar — ver Estado) |

\* Obligatoria una de las dos: `GATEWAY_UPSTREAMS_FILE` o `GATEWAY_UPSTREAMS`. En local se carga `.env` con `godotenv`, así que **ejecuta el gateway desde `gateway/`**.

### Upstreams (`gateway/internal/config/upstreams.json`)

```json
[
  { "name": "metapod", "prefix": "/v1/metapod", "target": "localhost:50051" }
]
```

| Campo | Descripción |
|---|---|
| `name` | Clave del servicio (enlaza con middlewares y con el `Override`) |
| `prefix` | Prefijo de ruta HTTP que se monta |
| `target` | Dirección del backend. Para metapod = **dirección gRPC** (`host:port`, sin esquema) |
| `protocol`, `stripPrefix`, `stream`, `timeout` | Solo aplican al **proxy genérico**; con `Override` se ignoran |

### metapod

| Variable | Default | Descripción |
|---|---|---|
| `LLAMA_URL` | `http://127.0.0.1:8081` | URL de llama-server |
| `CALLBACK_URL` | — | URL (con esquema y path) a la que se hace POST con el resultado |
| `GRPC_ADDR` | `127.0.0.1:50051` | Dirección de escucha gRPC |

---

## Inicialización

> **Nota local vs Docker:** en local el `target`/`GRPC_ADDR` usan `localhost`/`127.0.0.1`; en Docker usan los nombres de servicio (`metapod`, `llama`) y metapod debe escuchar en `0.0.0.0`. El compose ya hace esos overrides.

### Opción A — Local

```bash
# 1) metapod
cd services/metapod
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.server                      # gRPC en :50051

# 2) llama-server (opcional para probar solo el ack/202)
llama-server -m /ruta/modelo.gguf --host 127.0.0.1 --port 8081

# 3) gateway
cd gateway && go run ./cmd                 # HTTP en :8080
```

### Opción B — Docker

```bash
mkdir -p models && cp /ruta/modelo.gguf models/
echo "LLAMA_MODEL=modelo.gguf"        > .env
echo "CALLBACK_URL=https://dev.onyros.es/" >> .env
docker compose up --build
```

---

## Probar

```bash
curl -i -X POST localhost:8080/v1/metapod \
  -H 'content-type: application/json' \
  -d '{"brand":"acme","channel":"web","id":"123","prompt":"hola"}'
```

- **Respuesta inmediata:** `202` con `{"status":"accepted","id":"123"}` → la traducción HTTP→gRPC funciona.
- Con llama-server arriba, segundos después metapod hace POST a `CALLBACK_URL` con `{brand, channel, id, body, ok}`.

Health check: `curl localhost:8080/healthz` → `ok` (200).

---

## Flujo de una petición (`/v1/metapod`)

1. El cliente hace `POST /v1/metapod` con JSON `{brand, channel, id, prompt}`.
2. El **gateway** enruta por el prefijo `/v1/metapod` al handler `Override` de metapod, que **traduce el JSON a una llamada gRPC `Create`**.
3. **metapod** lanza la generación en background y **responde al instante** `CreateResponse{status:"accepted", id}`.
4. El gateway traduce esa respuesta gRPC a **`202` JSON** y la devuelve al cliente.
5. En background: metapod pide la generación a **llama-server** (HTTP) y, al terminar, hace **POST a `CALLBACK_URL`** con el resultado (o `ok:false` si falla), con reintentos y backoff.

---

## Añadir un nuevo servicio

**Servicio HTTP** → solo edita `upstreams.json` (data-driven, sin código):
```json
{ "name": "miservicio", "prefix": "/api/v1/miservicio", "target": "http://127.0.0.1:9100",
  "protocol": "http", "stripPrefix": true, "timeout": "5s" }
```

**Servicio gRPC con fachada HTTP** (como metapod) → un handler `Override`:
1. Define su RPC en el `.proto` y regenera stubs (`cd api && buf generate`).
2. Crea `gateway/internal/services/<nombre>/handler.go` con la traducción HTTP ⇄ gRPC.
3. Regístralo en `cmd/main.go`: `reg.Override("<nombre>", <nombre>.Builder)`.

---

## Estado actual

### ✅ Funciona
- Gateway HTTP→gRPC para metapod (traducción vía `Override`).
- metapod: ack inmediato + generación en background + callback con reintentos.
- Reverse proxy genérico data-driven (para futuros servicios HTTP).
- Middlewares: logging y API key.
- Build de Docker para gateway y metapod; `docker-compose` para gateway + metapod + llama.

### 🚧 Pendiente / por añadir
- **Durabilidad de los jobs:** metapod usa `asyncio.create_task`; si el proceso reinicia a mitad, se pierde el trabajo y no llega el callback. Plan: **arq + Valkey** (cola persistente, reintentos, límite de concurrencia hacia llama-server, idempotencia por `id`).
- **Valkey:** comentado en `docker-compose.yml`; reactivar cuando se implemente la cola.
- **Seguridad del callback:** firmarlo (HMAC) para que el receptor verifique el origen.
- **CORS:** `GATEWAY_ALLOWED_ORIGINS` se carga pero todavía no hay middleware que lo aplique (necesario si el cliente es navegador).
- **Graceful shutdown:** el gateway usa `http.ListenAndServe` directo; migrar a `http.Server` + `Shutdown(ctx)`.
- **profanity:** incompleto — `cmd/server/main.go` es `package profanity` (debería ser `package main`) y `cache/valkey.go` cierra el cliente al devolverlo (`defer client.Close()`) y usa `log.Fatal` en errores.

### ⚠️ A revisar antes de arrancar
- **Local:** el `gateway/.env` tiene la variable mal escrita (`GATEWAY_UPSTREAM_FILE` → debe ser `GATEWAY_UPSTREAMS_FILE`), y `upstreams.json` apunta a `metapod:50051` (sirve en Docker; en local usa `localhost:50051`).
- **Docker:** el `target` gRPC en `GATEWAY_UPSTREAMS` debería ser `metapod:50051` sin esquema (`http://` no es un target gRPC válido); verificar que conecta.
