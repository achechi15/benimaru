import asyncio

import grpc
from grpc_reflection.v1alpha import reflection

from profanity.v1 import profanity_pb2 as pb
from profanity.v1 import profanity_pb2_grpc as pb_grpc
from app.config import settings
from app.batcher import Batcher


class ProfanityService(pb_grpc.ProfanityServiceServicer):
    def __init__(self, batcher: Batcher):
        self.batcher = batcher

    async def Analyze(self, request, context):
        probas = await self.batcher.submit(request.text)
        return pb.AnalyzeResponse(probas=probas)


async def serve():
    batcher = Batcher(
        lang=settings.analyzer_lang,
        max_batch=settings.max_batch,
        max_delay=settings.max_delay,
        workers=settings.max_workers,
    )
    await batcher.start()

    server = grpc.aio.server()
    pb_grpc.add_ProfanityServiceServicer_to_server(ProfanityService(batcher), server)
    reflection.enable_server_reflection((
        pb.DESCRIPTOR.services_by_name["ProfanityService"].full_name,
        reflection.SERVICE_NAME,
    ), server)
    server.add_insecure_port(settings.grpc_addr)
    await server.start()
    print(f"[PROFANITY] gRPC escuchando en {settings.grpc_addr}")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
