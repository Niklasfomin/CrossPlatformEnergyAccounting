import logging
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from accumulation.docker import DockerManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("energy-monitor-api")


class InferenceRequest:
    def __init__(self, docker_manager: Optional[DockerManager] = None):
        # if docker_manager is None:
        #     docker_manager = self.get_docker_manager()
        self.docker_manager = docker_manager

    class ProcessMetrics(BaseModel):
        pid: int
        ppid: Optional[int] = None
        name: str = ""
        delta_cpu_ns: int = 0
        delta_io_bytes: int = 0
        delta_net_send_bytes: int = 0
        context_switches: int = 0
        syscall_count: int = 0
        delta_rss_memory: int = 0
        delta_cpu_time_psutil: int = 0
        delta_cpu_time_proc: int = 0
        instructions: int = 0
        cycles: int = 0
        branch_instructions: int = 0
        cache_misses: int = 0
        syscall_class_deltas: Dict[str, int] = Field(default_factory=dict)

    class ContainerInferenceRequest(BaseModel):
        container_name: str
        processes: List["InferenceRequest.ProcessMetrics"] = Field(default_factory=list)

    class PredictedProcessEnergyPerInterval(BaseModel):
        container_name: str
        predicted_energy: Optional[float] = None

    def create_app(self) -> FastAPI:
        app = FastAPI(
            title="Energy Accounting Inference API",
            description="API for preparing container process metrics for inference.",
            version="1.0.0",
        )

        @app.on_event("startup")
        async def startup_event() -> None:
            logger.info("Energy Accounting Inference API is starting up.")

        @app.on_event("shutdown")
        async def shutdown_event() -> None:
            logger.info("Energy Accounting Inference API is shutting down.")

        # @app.post(
        #     "/predict_energy/{container_name}",
        #     response_model=InferenceRequest.PredictedProcessEnergyPerInterval,
        # )
        # async def predict_energy(
        #     container_name: str,
        #     docker_manager: DockerManager = Depends(self.get_docker_manager),
        # ) -> InferenceRequest.PredictedProcessEnergyPerInterval:
        #     raw_process_metrics = (
        #         docker_manager.docker_container_to_pids_to_metrics.get(
        #             container_name, {}
        #         )
        #     )

        #     inference_request = InferenceRequest.ContainerInferenceRequest(
        #         container_name=container_name,
        #         processes=[
        #             InferenceRequest.ProcessMetrics(**metrics)
        #             for metrics in raw_process_metrics.values()
        #         ],
        #     )

        #     logger.info(
        #         "Prepared inference request for container '%s' with %d processes.",
        #         inference_request.container_name,
        #         len(inference_request.processes),
        #     )

        #     return InferenceRequest.PredictedProcessEnergyPerInterval(
        #         container_name=inference_request.container_name,
        #         predicted_energy=None,
        #     )

        return app
