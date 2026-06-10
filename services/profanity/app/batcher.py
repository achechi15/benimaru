import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from pysentimiento import create_analyzer


class Batcher:
    def __init__(self, lang="es", max_batch=32, max_delay=0.25, workers=4):
        self.max_batch = max_batch
        self.max_delay = max_delay
        self.queue: asyncio.Queue = asyncio.Queue()
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.analyzer = create_analyzer(task="sentiment", lang=lang)
        self.analyzer.predict("Texto de calentamiento para la primera inferencia.")
        print("[PROFANITY] warm-up completado")

    async def start(self):
        self._task = asyncio.create_task(self._loop())

    async def submit(self, text: str) -> dict:
        fut = asyncio.get_running_loop().create_future()
        await self.queue.put((text, fut))
        return await fut

    async def _loop(self):
        while True:
            text, fut = await self.queue.get()
            batch = [(text, fut)]
            start = time.monotonic()

            # Rellena el batch hasta max_batch o hasta agotar max_delay
            while len(batch) < self.max_batch:
                remaining = self.max_delay - (time.monotonic() - start)
                if remaining <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self.queue.get(), timeout=remaining))
                except asyncio.TimeoutError:
                    break

            texts = [t for t, _ in batch]
            try:
                results = await asyncio.get_running_loop().run_in_executor(
                    self.pool, self._infer, texts
                )
                for (_, f), r in zip(batch, results):
                    if not f.done():
                        f.set_result(r)
            except Exception as e:
                for _, f in batch:
                    if not f.done():
                        f.set_exception(e)

    def _infer(self, texts):
        if len(texts) == 1:
            return [dict(self.analyzer.predict(texts[0]).probas)]
        return [dict(r.probas) for r in self.analyzer.predict(texts)]
