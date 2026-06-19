import mimetypes

# import boto3
import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.config import settings

load_dotenv()

# Inicialización perezosa: NO construimos los clientes al importar para que el
# servicio arranque aunque falte GEMINI_API_KEY (el texto sigue funcionando).
# El cliente de genai lee GEMINI_API_KEY del entorno automáticamente.
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


# --- S3 vía boto3 (desactivado por ahora; descarga exclusivamente con httpx) ---
# _s3 = None
#
#
# def _get_s3():
#     """Cliente boto3 S3 perezoso.
#
#     Las credenciales se toman de la cadena estándar de boto3:
#     variables de entorno (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY /
#     AWS_REGION), rol IAM de la instancia o ~/.aws/credentials.
#     """
#     global _s3
#     if _s3 is None:
#         kwargs = {}
#         if settings.aws_region:
#             kwargs["region_name"] = settings.aws_region
#         _s3 = boto3.client("s3", **kwargs)
#     return _s3
#
#
# def _parse_s3_url(url: str) -> tuple[str, str] | None:
#     """Devuelve (bucket, key) si la url apunta a S3, o None si no lo es.
#
#     Soporta:
#       - s3://bucket/clave
#       - https://bucket.s3.region.amazonaws.com/clave  (virtual-hosted)
#       - https://s3.region.amazonaws.com/bucket/clave   (path-style)
#     """
#     from urllib.parse import unquote, urlparse
#
#     parsed = urlparse(url)
#
#     if parsed.scheme == "s3":
#         return parsed.netloc, parsed.path.lstrip("/")
#
#     host = parsed.hostname or ""
#     if not host.endswith("amazonaws.com"):
#         return None
#
#     key = unquote(parsed.path.lstrip("/"))
#     labels = host.split(".")
#     if "s3" in labels and labels[0] != "s3":
#         return labels[0], key
#     if key:
#         bucket, _, rest = key.partition("/")
#         return bucket, rest
#     return None
#
#
# def _download_from_s3(bucket: str, key: str) -> tuple[bytes, str]:
#     obj = _get_s3().get_object(Bucket=bucket, Key=key)
#     data = obj["Body"].read()
#     mime = (obj.get("ContentType") or "").split(";")[0].strip()
#     if not mime.startswith("image/"):
#         guessed, _ = mimetypes.guess_type(key)
#         mime = guessed or "image/jpeg"
#     return data, mime

# TODO(usuario): reemplazar por la system instruction definitiva.
# Debe forzar que el modelo responda EXACTAMENTE "true" o "false" para que
# _parse_bool pueda interpretar la respuesta de forma fiable.
SYSTEM_INSTRUCTION = (
    """
    Eres un clasificador visual binario estricto. Tu única tarea es analizar la imagen proporcionada y determinar si es una captura de pantalla de un chat de WhatsApp (en cualquiera de sus versiones: Android, iOS, WhatsApp Web o Escritorio).

    Analiza los elementos característicos como la disposición de los globos de texto, iconos de llamada/videollamada, barra de entrada de texto, estados de lectura (checks azules/grises) o la interfaz típica de la aplicación.

    Sigue estas reglas con un 100% de rigurosidad:
    - Responde exclusivamente con el dígito true si la imagen ES una captura de pantalla de un chat de WhatsApp.
    - Responde exclusivamente con el dígito false si la imagen NO es una captura de pantalla de un chat de WhatsApp (esto incluye fotos normales, capturas de interfaz de otras apps como Telegram, Instagram, Signal, o cualquier otro contenido).
    - NO incluyas introducciones, explicaciones, justificaciones ni puntuación.
    - NO uses formato Markdown (no agregues negritas, ni bloques de código).
    - Tu salida final debe contener exactamente un carácter.
    """
)


def _download_image(url: str) -> tuple[bytes, str]:
    return _download_http(url)


def _download_http(url: str) -> tuple[bytes, str]:
    with httpx.Client(timeout=settings.http_timeout, follow_redirects=True) as http:
        resp = http.get(url)
        resp.raise_for_status()
        data = resp.content

    mime = resp.headers.get("content-type", "").split(";")[0].strip()
    if not mime.startswith("image/"):
        guessed, _ = mimetypes.guess_type(url)
        mime = guessed or "image/jpeg"
    return data, mime


def _parse_bool(text: str) -> bool:
    normalized = text.strip().strip("\"'`").lower()
    if normalized.startswith("true"):
        return True
    if normalized.startswith("false"):
        return False
    raise ValueError(f"respuesta de Gemini no parseable a booleano: {text!r}")


def analyze_image(url: str) -> bool:
    """Descarga la imagen de la URL y pide a Gemini un veredicto booleano."""
    data, mime = _download_image(url)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0,
    )
    contents = [types.Part.from_bytes(data=data, mime_type=mime)]

    client = _get_client()
    last_err: Exception | None = None
    for model in (settings.gemini_model, settings.gemini_fallback_model):
        try:
            resp = client.models.generate_content(
                model=model, contents=contents, config=config
            )
            return _parse_bool(resp.text or "")
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[PROFANITY] fallo analizando imagen con {model}: {e}")

    raise RuntimeError(f"análisis de imagen falló: {last_err}")
