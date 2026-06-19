import mimetypes

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.config import settings

load_dotenv()

# El cliente lee GEMINI_API_KEY del entorno automáticamente.
client = genai.Client()

# TODO(usuario): reemplazar por la system instruction definitiva.
# Debe forzar que el modelo responda EXACTAMENTE "true" o "false" para que
# _parse_bool pueda interpretar la respuesta de forma fiable.
SYSTEM_INSTRUCTION = (
    "PLACEHOLDER pendiente de definir por el usuario. "
    "Analiza la imagen y responde únicamente con 'true' si contiene contenido "
    "profano o inapropiado, o 'false' en caso contrario. "
    "No incluyas ningún otro texto, explicación ni puntuación."
)


def _download_image(url: str) -> tuple[bytes, str]:
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
