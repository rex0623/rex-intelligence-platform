"""Main application entry point for RIP."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logger import get_logger
from app.gateways.line_gateway import LineGateway
from app.router.ai_router import AIRouter
from app.schemas.messages import LineWebhookRequest

logger = get_logger(__name__)

# Global instances
ai_router: AIRouter = AIRouter()
line_gateway: LineGateway = LineGateway(router=ai_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    # Startup
    logger.info("Starting RIP application")
    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down RIP application")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)


# Routes


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.

    Returns:
        Health status
    """
    logger.debug("Health check requested")

    return {
        "status": "healthy",
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/detailed", tags=["Health"])
async def detailed_health_check():
    """
    Detailed health check with worker status.

    Returns:
        Detailed health status
    """
    logger.debug("Detailed health check requested")

    if ai_router is None:
        logger.warning("AI Router is not initialized for detailed health check")
        router_health = {"router_status": "unavailable", "workers": {}}
    else:
        router_health = await ai_router.get_health()

    return {
        "status": "healthy",
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "router": router_health,
    }


@app.post("/line/webhook", tags=["LINE Gateway"])
async def line_webhook(request: Request):
    """
    LINE webhook endpoint.

    Args:
        request: Request object

    Returns:
        Response
    """
    if line_gateway is None:
        logger.error("LINE Gateway is not initialized")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Service unavailable"},
        )

    # Get signature from header
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()

    logger.info("LINE webhook received", extra={"signature_provided": bool(signature)})

    if not signature:
        logger.warning("Missing LINE signature header")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Missing X-Line-Signature header"},
        )

    decoded_body = body.decode("utf-8", errors="replace")

    # Verify signature
    if not line_gateway.verify_signature(signature, decoded_body):
        logger.warning("Invalid LINE signature")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Invalid signature"},
        )

    # Parse request
    try:
        webhook_request = LineWebhookRequest.model_validate_json(body)
    except Exception as e:
        logger.error(f"Failed to parse webhook request: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid request format"},
        )

    # Handle webhook
    try:
        result = await line_gateway.handle_webhook(webhook_request)
        logger.info("Webhook processed successfully")
        return {"status": "ok", "message": "Event received", "details": result}
    except Exception as e:
        logger.error(f"Failed to handle webhook: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal server error"},
        )


@app.get("/", tags=["Info"])
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "endpoints": {
            "health": "/health",
            "health_detailed": "/health/detailed",
            "line_webhook": "/line/webhook (POST)",
            "docs": "/docs",
            "redoc": "/redoc",
        },
    }


# Error handlers


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else None,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )
