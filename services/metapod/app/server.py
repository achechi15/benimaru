import asyncio
import grpc
from grpc_reflection.v1alpha import reflection

from metapod.v1 import metapod_pb2 as pb
from metapod.v1 import metapod_pb2_grpc as pb_grpc
from app.config import settings
from app.flow import run_flow, generate

_task = set()

class MetapodService(pb_grpc.MetapodServiceServicer):
    async def Create(self, request, context):
        task = asyncio.create_task(run_flow(request))
        _task.add(task)
        task.add_done_callback(_task.discard)
        return pb.CreateResponse(status="accepted", id=request.id)

    async def Analyze(self, request, context):
        # Síncrono: genera con el LLM y responde en la misma llamada.
        try:
            body = await generate(request.prompt)
        except Exception as e:
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
        return pb.AnalyzeResponse(body=body)

    async def Status(self, request, context):
        return pb.StatusResponse(ok=True)

async def serve():
    server = grpc.aio.server()
    pb_grpc.add_MetapodServiceServicer_to_server(MetapodService(), server)
    reflection.enable_server_reflection((
        pb.DESCRIPTOR.services_by_name["MetapodService"].full_name,
        reflection.SERVICE_NAME
    ), server)
    server.add_insecure_port(settings.grpc_addr)
    await server.start()
    print(f"[METAPOD] gRPC escuchando en {settings.grpc_addr}")
    await server.wait_for_termination()
    
if __name__ == "__main__":
    asyncio.run(serve())