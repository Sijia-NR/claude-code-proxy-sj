from fastapi import APIRouter, HTTPException, Request, Header, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from datetime import datetime
import uuid
from typing import Optional

from src.core.config import config
from src.core.logging import logger
from src.core.client import OpenAIClient
from src.models.claude import ClaudeMessagesRequest, ClaudeTokenCountRequest
from src.conversion.request_converter import convert_claude_to_openai
from src.conversion.response_converter import (
    convert_openai_to_claude_response,
    convert_openai_streaming_to_claude_with_cancellation,
)
from src.core.model_manager import model_manager

router = APIRouter()

# Get custom headers from config
custom_headers = config.get_custom_headers()

openai_client = OpenAIClient(
    config.openai_api_key,
    config.openai_base_url,
    config.request_timeout,
    api_version=config.azure_api_version,
    custom_headers=custom_headers,
    api_provider=config.api_provider,
    lmp_api_version=config.lmp_api_version,
)

async def validate_api_key(x_api_key: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    """Validate the client's API key from either x-api-key header or Authorization header."""
    client_api_key = None
    
    # Extract API key from headers
    if x_api_key:
        client_api_key = x_api_key
    elif authorization and authorization.startswith("Bearer "):
        client_api_key = authorization.replace("Bearer ", "")
    
    # Skip validation if ANTHROPIC_API_KEY is not set in the environment
    if not config.anthropic_api_key:
        return
        
    # Validate the client API key
    if not client_api_key or not config.validate_client_api_key(client_api_key):
        logger.warning(f"Invalid API key provided by client")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key. Please provide a valid Anthropic API key."
        )

@router.post("/v1/messages")
async def create_message(request: ClaudeMessagesRequest, http_request: Request, _: None = Depends(validate_api_key)):
    try:
        logger.debug(
            f"Processing Claude request: model={request.model}, stream={request.stream}"
        )

        # Generate unique request ID for cancellation tracking
        request_id = str(uuid.uuid4())

        # Convert Claude request to OpenAI format
        openai_request = convert_claude_to_openai(request, model_manager, config.api_provider)

        # Check if client disconnected before processing
        if await http_request.is_disconnected():
            raise HTTPException(status_code=499, detail="Client disconnected")

        if request.stream:
            # Streaming response - wrap in error handling
            try:
                openai_stream = openai_client.create_chat_completion_stream(
                    openai_request, request_id
                )
                return StreamingResponse(
                    convert_openai_streaming_to_claude_with_cancellation(
                        openai_stream,
                        request,
                        logger,
                        http_request,
                        openai_client,
                        request_id,
                        config.api_provider,
                        config.lmp_api_version,
                    ),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "*",
                    },
                )
            except HTTPException as e:
                # Convert to proper error response for streaming
                logger.error(f"Streaming error: {e.detail}")
                import traceback

                logger.error(traceback.format_exc())
                error_message = openai_client.classify_openai_error(e.detail)
                error_response = {
                    "type": "error",
                    "error": {"type": "api_error", "message": error_message},
                }
                return JSONResponse(status_code=e.status_code, content=error_response)
        else:
            # Non-streaming response
            openai_response = await openai_client.create_chat_completion(
                openai_request, request_id
            )
            claude_response = convert_openai_to_claude_response(
                openai_response, request, config.api_provider
            )
            return claude_response
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        logger.error(f"Unexpected error processing request: {e}")
        logger.error(traceback.format_exc())
        error_message = openai_client.classify_openai_error(str(e))
        raise HTTPException(status_code=500, detail=error_message)


@router.post("/v1/messages/count_tokens")
async def count_tokens(request: ClaudeTokenCountRequest, _: None = Depends(validate_api_key)):
    try:
        # For token counting, we'll use a simple estimation
        # In a real implementation, you might want to use tiktoken or similar

        total_chars = 0

        # Count system message characters
        if request.system:
            if isinstance(request.system, str):
                total_chars += len(request.system)
            elif isinstance(request.system, list):
                for block in request.system:
                    if hasattr(block, "text"):
                        total_chars += len(block.text)

        # Count message characters
        for msg in request.messages:
            if msg.content is None:
                continue
            elif isinstance(msg.content, str):
                total_chars += len(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if hasattr(block, "text") and block.text is not None:
                        total_chars += len(block.text)

        # Rough estimation: 4 characters per token
        estimated_tokens = max(1, total_chars // 4)

        return {"input_tokens": estimated_tokens}

    except Exception as e:
        logger.error(f"Error counting tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "openai_api_configured": bool(config.openai_api_key),
        "api_key_valid": config.validate_api_key(),
        "client_api_key_validation": bool(config.anthropic_api_key),
        "api_provider": config.api_provider,
        "lmp_api_version": config.lmp_api_version,
        "mock_models": config.mock_models,
    }


@router.get("/test-connection")
async def test_connection():
    """Test API connectivity to OpenAI"""
    try:
        # Simple test request to verify API connectivity
        test_response = await openai_client.create_chat_completion(
            {
                "model": config.small_model,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5,
            }
        )

        return {
            "status": "success",
            "message": "Successfully connected to OpenAI API",
            "model_used": config.small_model,
            "timestamp": datetime.now().isoformat(),
            "response_id": test_response.get("id", "unknown"),
        }

    except Exception as e:
        logger.error(f"API connectivity test failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "failed",
                "error_type": "API Error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
                "suggestions": [
                    "Check your OPENAI_API_KEY is valid",
                    "Verify your API key has the necessary permissions",
                    "Check if you have reached rate limits",
                ],
            },
        )


@router.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Claude-to-OpenAI API Proxy v1.0.0",
        "status": "running",
        "config": {
            "openai_base_url": config.openai_base_url,
            "max_tokens_limit": config.max_tokens_limit,
            "api_key_configured": bool(config.openai_api_key),
            "client_api_key_validation": bool(config.anthropic_api_key),
            "big_model": config.big_model,
            "small_model": config.small_model,
            "api_provider": config.api_provider,
            "lmp_api_version": config.lmp_api_version,
        },
        "endpoints": {
            "messages": "/v1/messages",
            "count_tokens": "/v1/messages/count_tokens",
            "health": "/health",
            "test_connection": "/test-connection",
        },
    }


# Model aliases for Claude models
CLAUDE_MODEL_ALIASES = {
    # Claude 4 Sonnet
    "claude-sonnet-4-20250514": "sonnet",
    "claude-sonnet-4-20250514-20250514": "sonnet",
    "claude sonnet 4": "sonnet",
    "claude-sonnet-4": "sonnet",
    # Claude 3.5 Sonnet
    "claude-3-5-sonnet-20241022": "sonnet",
    "claude-3-5-sonnet-20240620": "sonnet",
    "claude-3.5-sonnet": "sonnet",
    # Claude 3 Opus
    "claude-3-opus-20240229": "opus",
    "claude-3-opus-20240229": "opus",
    "claude-3-opus": "opus",
    # Claude 3 Haiku
    "claude-3-haiku-20240307": "haiku",
    "claude-3-5-haiku-20241022": "haiku",
    "claude-3-haiku": "haiku",
}


def get_model_info(model_id: str) -> Optional[dict]:
    """Get model info based on model ID, returns None if not found."""
    # Try exact match first
    tier = CLAUDE_MODEL_ALIASES.get(model_id)
    if not tier:
        # Try case-insensitive match
        model_id_lower = model_id.lower()
        for alias, t in CLAUDE_MODEL_ALIASES.items():
            if alias.lower() == model_id_lower:
                tier = t
                break

    if tier == "sonnet":
        return {
            "id": model_id,
            "name": "Claude 3.5 Sonnet",
            "display_name": f"Claude 3.5 Sonnet ({config.middle_model})",
            "type": "model",
            "created": 1708572800,
            "updated": 1728604800,
        }
    elif tier == "opus":
        return {
            "id": model_id,
            "name": "Claude 3 Opus",
            "display_name": f"Claude 3 Opus ({config.big_model})",
            "type": "model",
            "created": 1708572800,
            "updated": 1709241600,
        }
    elif tier == "haiku":
        return {
            "id": model_id,
            "name": "Claude 3 Haiku",
            "display_name": f"Claude 3 Haiku ({config.small_model})",
            "type": "model",
            "created": 1708572800,
            "updated": 1709241600,
        }
    return None


@router.get("/v1/models")
async def list_models(_: None = Depends(validate_api_key)):
    """List all available models (Claude API compatible)"""
    if not config.mock_models:
        raise HTTPException(status_code=404, detail="Not Found")

    models = []
    seen_models = set()

    # Add Claude model aliases
    for model_id, tier in CLAUDE_MODEL_ALIASES.items():
        if model_id not in seen_models:
            info = get_model_info(model_id)
            if info:
                models.append(info)
                seen_models.add(model_id)

    # Add raw configured models as fallback
    for model_id in [config.big_model, config.middle_model, config.small_model]:
        if model_id and model_id not in seen_models:
            models.append({
                "id": model_id,
                "name": model_id,
                "display_name": model_id,
                "type": "model",
                "created": 1708572800,
                "updated": 1708572800,
            })
            seen_models.add(model_id)

    return {
        "type": "list",
        "data": models,
        "has_more": False,
        "total": len(models),
    }


@router.get("/v1/models/{model_id}")
async def get_model(model_id: str, _: None = Depends(validate_api_key)):
    """Get model details (Claude API compatible)"""
    if not config.mock_models:
        raise HTTPException(status_code=404, detail="Not Found")

    # URL decode the model_id
    from urllib.parse import unquote
    model_id = unquote(model_id)

    # Try to find the model
    info = get_model_info(model_id)
    if info:
        return {
            "type": "model",
            "data": info,
        }

    # Check if it's a raw configured model
    if model_id in [config.big_model, config.middle_model, config.small_model]:
        return {
            "type": "model",
            "data": {
                "id": model_id,
                "name": model_id,
                "display_name": model_id,
                "type": "model",
                "created": 1708572800,
                "updated": 1708572800,
            },
        }

    raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
