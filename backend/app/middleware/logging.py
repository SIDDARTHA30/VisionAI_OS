import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api_request_logger")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Record start time
        start_time = time.time()
        
        # Extract metadata
        method = request.method
        url = str(request.url)
        client_ip = request.client.host if request.client else "unknown"

        logger.info(f"Incoming: {method} {url} from client IP: {client_ip}")

        try:
            response = await call_next(request)
            
            # Record execution duration
            duration = time.time() - start_time
            
            # Log response status code and execution duration
            logger.info(
                f"Response: {method} {url} - Status Code: {response.status_code} "
                f"- Process Time: {duration:.4f}s"
            )
            return response
            
        except Exception as exc:
            duration = time.time() - start_time
            logger.error(
                f"Request Failure: {method} {url} - Exception: {str(exc)} "
                f"- Duration: {duration:.4f}s"
            )
            raise exc
