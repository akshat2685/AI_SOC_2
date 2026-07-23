import asyncio
import structlog
from typing import Dict, Any
from .health import HealthChecker

logger = structlog.get_logger(__name__)

class ServiceRegistry:
    def __init__(self):
        self._services: Dict[str, Any] = {}
        
    def register(self, name: str, instance: Any):
        self._services[name] = instance
        logger.info(f"Registered service: {name}")
        
    def get(self, name: str) -> Any:
        return self._services.get(name)
        
    def list_all(self) -> list[str]:
        return list(self._services.keys())
        
class RuntimeKernel:
    def __init__(self):
        self.registry = ServiceRegistry()
        self.health_checker = HealthChecker(self.registry)
        
    def register_service(self, name: str, instance: Any):
        # Inject kernel reference if possible
        if hasattr(instance, "set_kernel"):
            instance.set_kernel(self)
        self.registry.register(name, instance)
        
    def get_service(self, name: str) -> Any:
        return self.registry.get(name)
        
    async def startup(self):
        logger.info("Starting up Runtime Kernel")
        for name in self.registry.list_all():
            service = self.registry.get(name)
            if hasattr(service, "connect") and callable(service.connect):
                logger.info(f"Connecting service: {name}")
                if asyncio.iscoroutinefunction(service.connect):
                    await service.connect()
                else:
                    service.connect()
                    
    async def shutdown(self):
        logger.info("Shutting down Runtime Kernel")
        services = self.registry.list_all()
        for name in reversed(services):
            service = self.registry.get(name)
            if hasattr(service, "disconnect") and callable(service.disconnect):
                logger.info(f"Disconnecting service: {name}")
                try:
                    if asyncio.iscoroutinefunction(service.disconnect):
                        await asyncio.wait_for(service.disconnect(), timeout=30.0)
                    else:
                        service.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting service {name}: {e}")
                    
    async def is_healthy(self) -> bool:
        health_status = await self.health_checker.aggregate()
        return health_status.get("overall") == "healthy"
