"""
Example: Using the AI Provider abstraction in FastAPI endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
import httpx


from src.ai import ModelRequest, get_active_provider

router = APIRouter(prefix="/api/agents", tags=["agents"])

# Module-level singleton to avoid B008 issue
_provider_dependency = Depends(lambda: get_active_provider())


@router.post(
    "/onboarding/extract",
    responses={
        500: {
            "description": "Provider call failed",
            "content": {
                "application/json": {
                    "example": {"detail": "Provider call failed: Connection timeout"}
                }
            },
        }
    },
)
async def extract_client_profile(
    transcript: str,
    provider=_provider_dependency,
):
    """
    Example endpoint: Extract client profile from transcript.

    Provider is automatically instantiated based on AI_PROVIDER env var.

    **Returns:**
    - `success`: Boolean indicating successful extraction
    - `content`: Extracted profile as JSON string
    - `provider`: Name of provider used (ollama, anthropic, openai)
    - `cost_estimate`: Estimated cost in USD
    - `tokens_used`: Number of tokens consumed

    **Errors:**
    - 500: Provider call failed (timeout, invalid response, etc.)
    """
    try:
        # Define extraction schema
        extraction_schema = {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "budget": {"type": "number"},
                "services_needed": {"type": "array", "items": {"type": "string"}},
                "timeline": {"type": "string"},
            },
            "required": ["company_name"],
        }

        # Create model request
        request = ModelRequest(
            prompt=f"Extract client information from this transcript:\n\n{transcript}",
            schema=extraction_schema,
            temperature=0.3,  # Lower temperature for consistency
            max_tokens=1000,
        )

        # Call provider (works with any configured provider)
        response = await provider.call(request)

        return {
            "success": True,
            "content": response.content,
            "provider": response.provider,
            "cost_estimate": response.cost_estimate,
            "tokens_used": response.tokens_used,
        }

    except TimeoutError as e:
        msg = f"Provider call failed: {e!s}"
        raise HTTPException(status_code=500, detail=msg) from e
    except httpx.RequestError as e:
        msg = f"Provider call failed: {e!s}"
        raise HTTPException(status_code=500, detail=msg) from e


@router.get(
    "/health",
    responses={
        503: {
            "description": "Provider unreachable",
            "content": {
                "application/json": {
                    "example": {"detail": "Provider unreachable: Connection refused"}
                }
            },
        }
    },
)
async def health_check(provider=_provider_dependency):
    """
    Health check: Verify provider connectivity.

    Useful for monitoring and debugging.

    **Returns:**
    - `status`: "healthy" or "unhealthy"
    - `provider`: Class name of provider in use

    **Errors:**
    - 503: Provider unreachable (service unavailable)
    """
    try:
        is_valid = provider.validate_credentials()
        return {
            "status": "healthy" if is_valid else "unhealthy",
            "provider": provider.__class__.__name__,
        }
    except httpx.RequestError as e:
        msg = f"Provider unreachable: {e!s}"
        raise HTTPException(status_code=503, detail=msg) from e


@router.post(
    "/agents/launch-brief",
    responses={
        500: {
            "description": "Failed to generate launch brief",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Failed to generate launch brief: Invalid profile format"
                    }
                }
            },
        }
    },
)
async def generate_launch_brief(
    client_profile: dict,
    provider=_provider_dependency,
):
    """
    Example endpoint: Generate launch brief using approved client context.

    Same provider abstraction, different agent.

    **Returns:**
    - `brief`: Generated launch brief as JSON string
    - `provider`: Name of provider used
    - `cost_estimate`: Estimated cost in USD

    **Errors:**
    - 500: Failed to generate launch brief (provider error, invalid input, etc.)
    """
    try:
        request = ModelRequest(
            prompt=f"""
Using this approved client profile:
{client_profile}

Generate a launch brief including:
1. Target market
2. Key messaging
3. Campaign timeline
            """,
            schema={
                "type": "object",
                "properties": {
                    "target_market": {"type": "string"},
                    "messaging": {"type": "array", "items": {"type": "string"}},
                    "timeline_weeks": {"type": "integer"},
                },
            },
            temperature=0.5,
            max_tokens=1500,
        )

        response = await provider.call(request)

        return {
            "brief": response.content,
            "provider": response.provider,
            "cost_estimate": response.cost_estimate,
        }

    except httpx.RequestError as e:
        msg = f"Failed to generate launch brief: {e!s}"
        raise HTTPException(status_code=500, detail=msg) from e
