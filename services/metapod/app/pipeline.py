import time

import httpx

from app.config import settings
from app.flow_generator import normalize_prompt
from app.gemini import call_gemini_chat_mode

INSTRUCTION = """
    Eres un experto en whatsapp flows. Genera un flujo de whatsapp basado en la siguiente descripción.
    """

ALPACA_PROMPT = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request. Make sure your response is in JSON Format.

    ### Instruction:
    {}

    ### Input:
    {}

    ### Response:
    {}
    """


def local_model_response(prompt: str) -> str:
    full_input = ALPACA_PROMPT.format(INSTRUCTION, prompt, "")

    payload = {
        "prompt": full_input,
        "n_predict": 4096,
        "stream": False,
        "repeat_penalty": 1.0,
        "top_k": 10,
        "top_p": 0.15,
        "temperature": 0.0,
        "stop": ["</s>", "### Instruction:", "### Input:"],
    }

    resp = httpx.post(f"{settings.llama_url}/completion", json=payload, timeout=None)
    resp.raise_for_status()
    full_response = resp.json().get("content", "")

    print("\n\n--- Fin de la generación local ---\n")
    return full_response


def refine_with_gemini(prompt: str) -> str:
    history = [
        {
            "role": "user",
            "parts": [{"text": """Crea un flujo de 3 pantallas para alquilar un coche:

Pantalla 1 - Vehículo:
- Categoría del vehículo: selección única con precios por día (Económico, Compacto, Familiar, SUV, Premium)
- Botón "Siguiente" que navegue a la pantalla 2

Pantalla 2 - Fechas:
- Fecha de recogida (selector de fecha)
- Fecha de devolución (selector de fecha)
- Hora de recogida (desplegable)
- Botón "Siguiente" que navegue a la pantalla 3

Pantalla 3 - Datos del conductor (terminal):
- Nombre completo
- DNI
- Teléfono
- Botón "Reservar" que complete el flujo enviando todos los datos
                      """}]
        },
        {
            "role": "model",
            "parts": [{"text": """
{
    "version": "7.2",
    "screens": [
        {
            "id": "CONSULTA_SCREEN",
            "title": "Consulta legal",
            "terminal": true,
            "layout": {
                "type": "SingleColumnLayout",
                "children": [
                    {
                        "type": "Form",
                        "name": "consulta_form",
                        "children": [
                            {
                                "type": "Dropdown",
                                "name": "area_legal",
                                "label": "Área legal",
                                "required": true,
                                "data-source": [
                                    {"id": "familia", "title": "Familia"},
                                    {"id": "laboral", "title": "Laboral"},
                                    {"id": "penal", "title": "Penal"},
                                    {"id": "civil", "title": "Civil"},
                                    {"id": "mercantil", "title": "Mercantil"},
                                    {"id": "inmobiliario", "title": "Inmobiliario"}
                                ]
                            },
                            {
                                "type": "TextInput",
                                "name": "descripcion_caso",
                                "label": "Describe brevemente tu caso",
                                "input-type": "text",
                                "required": true
                            },
                            {
                                "type": "RadioButtonsGroup",
                                "name": "urgencia",
                                "label": "Urgencia",
                                "required": true,
                                "data-source": [
                                    {"id": "normal", "title": "Normal"},
                                    {"id": "urgente", "title": "Urgente"},
                                    {"id": "muy_urgente", "title": "Muy urgente"}
                                ]
                            },
                            {
                                "type": "TextInput",
                                "name": "nombre",
                                "label": "Nombre",
                                "input-type": "text",
                                "required": true
                            },
                            {
                                "type": "TextInput",
                                "name": "email",
                                "label": "Email",
                                "input-type": "email",
                                "required": true
                            },
                            {
                                "type": "TextInput",
                                "name": "telefono",
                                "label": "Teléfono",
                                "input-type": "phone",
                                "required": true
                            },
                            {
                                "type": "OptIn",
                                "name": "privacidad",
                                "label": "Acepto la política de privacidad",
                                "required": true
                            },
                            {
                                "type": "Footer",
                                "label": "Solicitar consulta",
                                "on-click-action": {
                                    "name": "complete",
                                    "payload": {
                                        "area_legal": "${form.area_legal}",
                                        "descripcion_caso": "${form.descripcion_caso}",
                                        "urgencia": "${form.urgencia}",
                                        "nombre": "${form.nombre}",
                                        "email": "${form.email}",
                                        "telefono": "${form.telefono}",
                                        "privacidad": "${form.privacidad}"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        }
    ]
}
                      """}]
        },
        {
            "role": "user",
            "parts": [{"text": "Flujo de alquiler de auto en 3 pantallas.\n\nPantalla 1 - Fechas y ubicación:\n- Sucursal de recogida (Dropdown: Aeropuerto, Centro ciudad, Zona norte, Zona sur)\n- Fecha de recogida (DatePicker, obligatorio)\n- Hora de recogida (Dropdown: 8:00, 10:00, 12:00, 14:00, 16:00, 18:00)\n- Fecha de devolución (DatePicker, obligatorio)\n- ¿Devolución en otra sucursal? (Switch)\nBotón 'Siguiente'\n\nPantalla 2 - Tipo de vehículo:\n- Categoría (RadioButtons: Económico, Compacto, Sedán, SUV, Van, Lujo)\n- Transmisión (RadioButtons: Manual, Automática)\n- Extras (CheckboxGroup: GPS, Silla de bebé, Seguro premium, Conductor adicional)\nBotón 'Siguiente'\n\nPantalla 3 - Datos del conductor:\n- Nombre completo (obligatorio)\n- Email (obligatorio)\n- Teléfono (obligatorio)\n- Número de licencia (obligatorio)\n- País de emisión de licencia (Dropdown: México, USA, España, Argentina, Colombia, Otro)\nBotón 'Reservar vehículo'"}]
        },
        {
            "role": "model",
            "parts": [{"text": """
{
    "version": "7.2",
    "screens": [
        {
            "id": "VEHICULO_SCREEN",
            "title": "Alquiler coche",
            "layout": {
                "type": "SingleColumnLayout",
                "children": [
                    {
                        "type": "Form",
                        "name": "vehiculo_form",
                        "children": [
                            {
                                "type": "TextHeading",
                                "text": "Elige tu vehículo"
                            },
                            {
                                "type": "RadioButtonsGroup",
                                "name": "categoria",
                                "label": "Categoría",
                                "required": true,
                                "data-source": [
                                    {"id": "economico", "title": "Económico - 25€/día"},
                                    {"id": "compacto", "title": "Compacto - 35€/día"},
                                    {"id": "familiar", "title": "Familiar - 50€/día"},
                                    {"id": "suv", "title": "SUV - 65€/día"},
                                    {"id": "premium", "title": "Premium - 90€/día"}
                                ]
                            },
                            {
                                "type": "Footer",
                                "label": "Siguiente",
                                "on-click-action": {
                                    "name": "navigate",
                                    "next": {
                                        "type": "screen",
                                        "name": "FECHAS_SCREEN"
                                    },
                                    "payload": {
                                        "categoria": "${form.categoria}"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        },
        {
            "id": "FECHAS_SCREEN",
            "title": "Fechas de alquiler",
            "data": {
                "categoria": {
                    "type": "string",
                    "__example__": "compacto"
                }
            },
            "layout": {
                "type": "SingleColumnLayout",
                "children": [
                    {
                        "type": "Form",
                        "name": "fechas_form",
                        "children": [
                            {
                                "type": "DatePicker",
                                "name": "fecha_recogida",
                                "label": "Fecha de recogida",
                                "required": true
                            },
                            {
                                "type": "DatePicker",
                                "name": "fecha_devolucion",
                                "label": "Fecha de devolución",
                                "required": true
                            },
                            {
                                "type": "Dropdown",
                                "name": "hora_recogida",
                                "label": "Hora de recogida",
                                "required": true,
                                "data-source": [
                                    {"id": "08:00", "title": "08:00"},
                                    {"id": "10:00", "title": "10:00"},
                                    {"id": "12:00", "title": "12:00"},
                                    {"id": "14:00", "title": "14:00"},
                                    {"id": "16:00", "title": "16:00"},
                                    {"id": "18:00", "title": "18:00"}
                                ]
                            },
                            {
                                "type": "Footer",
                                "label": "Siguiente",
                                "on-click-action": {
                                    "name": "navigate",
                                    "next": {
                                        "type": "screen",
                                        "name": "CONDUCTOR_SCREEN"
                                    },
                                    "payload": {
                                        "categoria": "${data.categoria}",
                                        "fecha_recogida": "${form.fecha_recogida}",
                                        "fecha_devolucion": "${form.fecha_devolucion}",
                                        "hora_recogida": "${form.hora_recogida}"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        },
        {
            "id": "CONDUCTOR_SCREEN",
            "title": "Datos del conductor",
            "terminal": true,
            "data": {
                "categoria": {
                    "type": "string",
                    "__example__": "compacto"
                },
                "fecha_recogida": {
                    "type": "string",
                    "__example__": "1710460800"
                },
                "fecha_devolucion": {
                    "type": "string",
                    "__example__": "1711065600"
                },
                "hora_recogida": {
                    "type": "string",
                    "__example__": "10:00"
                }
            },
            "layout": {
                "type": "SingleColumnLayout",
                "children": [
                    {
                        "type": "Form",
                        "name": "conductor_form",
                        "children": [
                            {
                                "type": "TextInput",
                                "name": "nombre",
                                "label": "Nombre completo",
                                "required": true,
                                "input-type": "text"
                            },
                            {
                                "type": "TextInput",
                                "name": "dni",
                                "label": "DNI",
                                "required": true,
                                "input-type": "text"
                            },
                            {
                                "type": "TextInput",
                                "name": "telefono",
                                "label": "Teléfono",
                                "required": true,
                                "input-type": "phone"
                            },
                            {
                                "type": "Footer",
                                "label": "Reservar",
                                "on-click-action": {
                                    "name": "complete",
                                    "payload": {
                                        "categoria": "${data.categoria}",
                                        "fecha_recogida": "${data.fecha_recogida}",
                                        "fecha_devolucion": "${data.fecha_devolucion}",
                                        "hora_recogida": "${data.hora_recogida}",
                                        "nombre": "${form.nombre}",
                                        "dni": "${form.dni}",
                                        "telefono": "${form.telefono}"
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        }
    ]
}
                      """}]
        }
    ]

    system_instruction = (
        "Eres un experto en WhatsApp Flows 7.2. "
        "Tu tarea es convertir descripciones o estructuras lógicas en JSONs válidos. "
        "Responde exclusivamente con el objeto JSON."
    )
    user_message = f"Convierte esta estructura base en el JSON final siguiendo el formato anterior: {prompt}"
    output = call_gemini_chat_mode(system_instruction, history, user_message)
    print("Respuesta de Gemini supervision:\n", output, "\n--- Fin de la respuesta de Gemini ---\n")
    return output


def run_pipeline(prompt: str) -> str:
    """Pipeline bloqueante: Gemini (normaliza) -> LLM local -> Gemini (refina)."""
    print("Normalizando prompt...")
    start = time.time()
    normalized = normalize_prompt(prompt)
    print(f"Prompt normalizado en {time.time() - start:.2f} s\n")

    print("Ejecutando modelo local...")
    start = time.time()
    structural_base = local_model_response(normalized)
    print(f"Modelo local completado en {time.time() - start:.2f} s\n")

    print("Refinando JSON final...")
    start = time.time()
    final_json = refine_with_gemini(structural_base)
    print(f"Refinamiento completado en {time.time() - start:.2f} s\n")

    return final_json
