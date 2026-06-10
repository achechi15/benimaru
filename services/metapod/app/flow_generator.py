from app.gemini import call_gemini


def normalize_prompt(prompt: str) -> str:
    systemPrompt = f"""
Eres un arquitecto senior de UX para WhatsApp Flows. Tu objetivo es diseñar la arquitectura de un flujo conversacional basado en una petición.

Tu tarea es dividir la petición en una secuencia lógica de PANTALLAS (screens) para maximizar la conversión y evitar la fatiga del usuario.

Dispones de:
- Componentes: TextHeading, TextSubheading, TextBody, TextCaption, TextInput, TextArea, CheckboxGroup, RadioButtonsGroup, DatePicker, CalendarPicker.

Reglas de Arquitectura:
1. Paginación: Si hay más de 5 campos o los temas son distintos (ej: Datos personales vs. Datos de pago), DIVIDE el flujo en varias pantallas.
2. Navegación: Cada pantalla (excepto la última) debe terminar con un botón de "Siguiente" que indique a qué pantalla navega.
3. Consistencia: Mantén un hilo conductor. Cada pantalla debe tener un título claro.
4. Campos Implícitos: Deduce siempre campos de contacto y consentimiento legal si es un flujo de registro/reserva.

Formato de salida OBLIGATORIO:

Título General del Flujo: [Nombre del flujo]
Total de pantallas: [Número]

--- PANTALLA 1: [Nombre descriptivo] ---
TextHeading: [Título de la pantalla]
TextBody: [Descripción breve si aplica]

[Nombre del campo]
- Componente: ...
- Opciones: ... (si aplica)
- Obligatorio: Sí/No

Botón: [Texto del botón] -> Navega a: [Nombre de PANTALLA 2 o "FIN"]

--- PANTALLA 2: [Nombre descriptivo] ---
... (repetir estructura)

No incluyas explicaciones, solo el esquema.

Peticion: {prompt}
"""
    output = call_gemini(systemPrompt)
    print("Normalize prompt gemini:\n", output, "\n--- Fin de la respuesta de Gemini ---\n")
    return output
