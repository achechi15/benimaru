# Servicio Profanity

Servicio gRPC en **Python** (`grpc.aio`) que analiza contenido potencialmente ofensivo. Tiene dos modos:

- **Texto** — clasifica un texto con [`pysentimiento`](https://github.com/pysentimiento/pysentimiento) y devuelve un mapa de probabilidades por etiqueta.
- **Imagen** — descarga una imagen desde una URL (p. ej. S3) y pregunta a **Gemini** si contiene contenido profano/inapropiado, devolviendo un booleano.

Escucha gRPC en `GRPC_ADDR` (por defecto `127.0.0.1:50052`, en Docker `0.0.0.0:50052`). No se expone directamente: el **gateway** le habla por gRPC y traduce desde HTTP/JSON.

---

## Arquitectura interna

```
            gRPC
Gateway ───────────────► Profanity (Python, :50052)
                          │
            AnalyzeText ──┤──► Batcher (pysentimiento, en pool de hilos)
                          │
           AnalyzeImage ──┴──► gemini.analyze_image
                                  ├─ httpx: descarga la imagen de la URL
                                  └─ Gemini: veredicto "true"/"false"
```

- **`app/server.py`** — servidor gRPC con los dos RPCs (`AnalyzeText`, `AnalyzeImage`).
- **`app/batcher.py`** — agrupa peticiones de texto en lotes (`max_batch` / `max_delay`) y ejecuta la inferencia en un `ThreadPoolExecutor`. Hace un warm-up al arrancar.
- **`app/gemini.py`** — descarga la imagen, infiere el mime-type y llama a Gemini con una `system_instruction`. Parsea la respuesta a booleano.
- **`app/config.py`** — settings desde entorno / `.env`.

---

## Contrato gRPC

Definido en [`api/proto/profanity/v1/profanity.proto`](../../api/proto/profanity/v1/profanity.proto):

```proto
service ProfanityService {
  rpc AnalyzeText(AnalyzeTextRequest) returns (AnalyzeTextResponse);
  rpc AnalyzeImage(AnalyzeImageRequest) returns (AnalyzeImageResponse);
}

message AnalyzeTextRequest  { string text = 1; }
message AnalyzeTextResponse { map<string, double> probas = 1; }

message AnalyzeImageRequest  { string url = 1; }
message AnalyzeImageResponse { bool profanity_check = 1; }
```

| RPC | Entrada | Salida |
|---|---|---|
| `AnalyzeText` | `text` (string) | `probas`: mapa etiqueta → probabilidad (`double`) |
| `AnalyzeImage` | `url` (string, URL de la imagen) | `profanity_check`: `true` / `false` |

---

## Cómo enviar datos

> En producción **siempre** se entra por el gateway en `POST /v1/profanity` (HTTP/JSON). El gateway decide texto vs imagen según el cuerpo. Ver [el documento del gateway](../../gateway/README.md).

### A través del gateway (forma habitual)

**Texto** (campo `text`):

```bash
curl -s -X POST localhost:8080/v1/profanity \
  -H 'content-type: application/json' \
  -d '{"text":"eres un idiota"}'
```

Respuesta (mapa de probabilidades de `pysentimiento`):

```json
{ "NEG": 0.91, "NEU": 0.07, "POS": 0.02 }
```

**Imagen** (campo `url`):

```bash
curl -s -X POST localhost:8080/v1/profanity \
  -H 'content-type: application/json' \
  -d '{"url":"https://mi-bucket.s3.amazonaws.com/img/123.jpg"}'
```

Respuesta:

```json
{ "profanity_check": true }
```

**Texto + imagen** (ambos campos): se analizan en paralelo y la respuesta combina los dos resultados:

```bash
curl -s -X POST localhost:8080/v1/profanity \
  -H 'content-type: application/json' \
  -d '{"text":"eres un idiota","url":"https://mi-bucket.s3.amazonaws.com/img/123.jpg"}'
# -> {"text":{"NEG":0.91,"NEU":0.07,"POS":0.02},"image":{"profanity_check":true}}
```

Regla de enrutado en el gateway:

- Solo **`text`** → `AnalyzeText` (mapa de probabilidades).
- Solo **`url`** → `AnalyzeImage` (`{"profanity_check": bool}`).
- **Ambos** → `AnalyzeText` + `AnalyzeImage` en paralelo → `{"text": {...}, "image": {...}}`.

### Directo por gRPC (para depurar)

Con reflection habilitado puedes usar `grpcurl`:

```bash
# Texto
grpcurl -plaintext -d '{"text":"eres un idiota"}' \
  localhost:50052 profanity.v1.ProfanityService/AnalyzeText

# Imagen
grpcurl -plaintext -d '{"url":"https://.../img.jpg"}' \
  localhost:50052 profanity.v1.ProfanityService/AnalyzeImage
```

---

## Análisis de imagen con Gemini

`app/gemini.py`:

1. Descarga la imagen con `httpx` (sigue redirects, timeout `http_timeout`). **Se asume que la URL es accesible** (pública o presignada). Si el bucket es privado habría que añadir credenciales AWS.
2. Determina el mime-type por la cabecera `Content-Type`, con fallback por extensión y a `image/jpeg`.
3. Llama a Gemini (`gemini_model`, con fallback a `gemini_fallback_model`) pasando los bytes y la `SYSTEM_INSTRUCTION`, con `temperature=0`.
4. Parsea la respuesta: empieza por `true` → `True`, por `false` → `False`. Cualquier otra cosa es error.

> **Pendiente:** la constante `SYSTEM_INSTRUCTION` en `app/gemini.py` es un **placeholder** (`TODO(usuario)`). Debe forzar que el modelo responda **exactamente** `true` o `false`. Sustitúyela por la instrucción definitiva.

---

## Configuración

Variables (vía entorno o `.env`; `app/config.py`):

| Variable | Default | Descripción |
|---|---|---|
| `GRPC_ADDR` | `127.0.0.1:50052` | Dirección de escucha gRPC |
| `ANALYZER_LANG` | `es` | Idioma del analizador de texto (`pysentimiento`) |
| `MAX_BATCH` | `32` | Tamaño máximo de lote de texto |
| `MAX_DELAY` | `0.25` | Espera máxima (s) para llenar el lote |
| `MAX_WORKERS` | `4` | Hilos del pool de inferencia de texto |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modelo Gemini para imágenes |
| `GEMINI_FALLBACK_MODEL` | `gemini-2.5-flash-lite` | Modelo de respaldo |
| `HTTP_TIMEOUT` | `15.0` | Timeout (s) de descarga de imagen |
| `GEMINI_API_KEY` | — | **Obligatoria para imágenes.** La lee el cliente `google-genai` |

---

## Manejo de errores

- **Texto:** si `pysentimiento` falla, el RPC propaga el error gRPC.
- **Imagen:** si falla la descarga, la llamada a Gemini o el parseo, `AnalyzeImage` aborta con `INTERNAL` y el gateway responde **`502`**. No hay fail-open ni fail-closed: el error se hace visible.

---

## Ejecutar en local

```bash
cd services/profanity
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=...        # necesario para AnalyzeImage
python -m app.server             # gRPC en :50052
```

> El primer arranque descarga el modelo de `pysentimiento` y hace warm-up; puede tardar.

---

## Regenerar stubs

Los stubs Python (`profanity/v1/*_pb2*.py`) y Go (en el gateway) se generan desde el `.proto`. Tras editar `profanity.proto`:

```bash
# Go (gateway)
cd api && buf generate

# Python (este servicio): usar grpcio-tools, NO el plugin remoto de buf.
# Así el "gencode" coincide con el runtime de protobuf instalado en el
# contenedor (si no, falla con VersionError gencode/runtime).
cd ..
python -m grpc_tools.protoc -I api/proto \
  --python_out services/profanity \
  --grpc_python_out services/profanity \
  api/proto/profanity/v1/profanity.proto
```

> Importante: genera los stubs Python con la misma versión de `protobuf` que
> queda instalada por `requirements.txt` (hoy `6.33.x`). El plugin remoto de
> buf produce un gencode más nuevo (7.x) incompatible con ese runtime.
