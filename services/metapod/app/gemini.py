from google import genai
from google.genai import types
from dotenv import load_dotenv
import time

load_dotenv()

client = genai.Client()

model = "gemini-3-flash-preview"
fallback_model = "gemini-2.5-flash"  # Modelo de respaldo si el principal falla


def call_gemini(prompt: str) -> str:
    max_retries = 2
    base_delay = 2

    current_model = model

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(model=current_model, contents=prompt)
            return response.text.strip()
        except Exception as e:
            # Si es el último intento y tenemos un fallback disponible, probamos con el fallback
            if attempt == max_retries and current_model == model:
                print(f"Error persistente con {model}: {e}. Cambiando a {fallback_model}...")
                current_model = fallback_model
                try:
                    response = client.models.generate_content(model=current_model, contents=prompt)
                    return response.text.strip()
                except Exception as e2:
                    raise Exception(f"Fallaron ambos modelos: {e} -> {e2}")

            if attempt < max_retries and ('503' in str(e) or '429' in str(e)):
                time.sleep(base_delay * (attempt + 1))
                continue

            # Si falla por algo que no es retry-able o se acabaron los intentos
            if current_model == model:
                print(f"Fallo no recuperable con {model}: {e}. Intentando fallback {fallback_model}...")
                current_model = fallback_model
                try:
                    response = client.models.generate_content(model=current_model, contents=prompt)
                    return response.text.strip()
                except Exception as e2:
                    raise Exception(f"Fallaron ambos modelos: {e} -> {e2}")

            raise e


def call_gemini_chat_mode(system_prompt: str, history: list, user_prompt: str) -> str:
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.1,
        response_mime_type="application/json"
    )

    # Asegurar que history tenga el formato correcto para la librería
    formatted_history = []
    for msg in history:
        parts = msg.get('parts', [])
        formatted_parts = []
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, str):
                    formatted_parts.append({"text": part})
                elif isinstance(part, dict) and "text" in part:
                    formatted_parts.append(part)
                else:
                    formatted_parts.append({"text": str(part)})

        formatted_history.append({
            "role": msg.get("role"),
            "parts": formatted_parts
        })

    messages = formatted_history + [{"role": "user", "parts": [{"text": user_prompt}]}]

    max_retries = 2
    base_delay = 2

    current_model = model

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(model=current_model, contents=messages, config=config)
            return response.text.strip()
        except Exception as e:
            if attempt < max_retries and ('503' in str(e) or '429' in str(e)):
                print(f"Error {e}. Retrying {attempt+1}/{max_retries}...")
                time.sleep(base_delay * (attempt + 1))
                continue

            if current_model == model:
                print(f"Error crítico o agotados reintentos con {model}: {e}. Cambiando a {fallback_model}")
                try:
                    response = client.models.generate_content(model=fallback_model, contents=messages, config=config)
                    return response.text.strip()
                except Exception as e2:
                    raise Exception(f"Fallaron ambos modelos en chat: {e} -> {e2}")

            raise e
