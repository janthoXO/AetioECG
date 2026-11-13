from concurrent import futures

import grpc

from aetioecg.core import EcgSource, get_ecg, list_options
from aetioecg.v1 import ecg_pb2_grpc
from aetioecg.v1.ecg_pb2 import Ecg, EcgOptions, EcgRequest, ListOptionsRequest


class _Servicer(ecg_pb2_grpc.EcgServiceServicer):
    def __init__(self, source: EcgSource):
        self.source = source

    def ListOptions(self, request: ListOptionsRequest, context: grpc.ServicerContext) -> EcgOptions:
        try:
            return list_options(self.source)
        except OSError as e:  # dataset unreachable
            context.abort(grpc.StatusCode.UNAVAILABLE, str(e))

    def GetEcg(self, request: EcgRequest, context: grpc.ServicerContext) -> Ecg:
        try:
            return get_ecg(self.source, request)
        except ValueError as e:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except OSError as e:
            context.abort(grpc.StatusCode.UNAVAILABLE, str(e))


def build_server(source: EcgSource, address: str) -> grpc.Server:
    """aetioecg.v1.EcgService on `address` (e.g. "127.0.0.1:50051"), plaintext. Call start() on the result."""
    # ponytail: no TLS, health or reflection service; add grpcio-health-checking when an orchestrator probes it.
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    ecg_pb2_grpc.add_EcgServiceServicer_to_server(_Servicer(source), server)
    server.add_insecure_port(address)
    return server
