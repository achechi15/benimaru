import asyncio
import httpx
from app.config import settings

async def generate(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            f"{settings.llama_url}/completion",
            json={"prompt": prompt, "stream": False}
        )
        r.raise_for_status()
        return r.json()["content"]

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