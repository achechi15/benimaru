import asyncio
import httpx
from app.config import settings
from app.pipeline import run_pipeline

async def generate(prompt: str) -> str:
    # El pipeline (Gemini -> llama -> Gemini) es bloqueante; lo lanzamos en un
    # hilo para no bloquear el event loop de grpc.aio.
    return await asyncio.get_running_loop().run_in_executor(None, run_pipeline, prompt)

async def send_callback(req, body: str, ok: bool):
    if not settings.callback_url:
        return
    payload = {"brand": req.brand, "channel": req.channel, "id": req.id, "body": body, "ok": ok}
    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(3):
            try:
                resp = await client.post(settings.callback_url, json=payload)
                resp.raise_for_status()
                return
            except Exception:
                await asyncio.sleep(2 ** attempt)
                
async def run_flow(req):
    try:
        body = await generate(req.prompt)
        await send_callback(req, body, ok=True)
    except Exception as e:
        await send_callback(req, str(e), ok=False)