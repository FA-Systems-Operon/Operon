"""
Example: Using the AI Provider abstraction in FastAPI endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from src.ai import get_active_provider, ModelRequest

router = APIRouter(prefix="/api/agents", tags=["agents"])


def get_provider():
    """Dependency for getting the active AI provider."""
    return get_active_provider()


@router.post("/onboarding/extract")
async def extract_client_profile(
    transcript: str,
    provider = Depends(get_provider)
):
    """
    Example endpoint: Extract client profile from transcript.
    Provider is automatically instantiated based on AI_PROVIDER env var.
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
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Provider call failed: {str(e)}")


@router.get("/health")
async def health_check(provider = Depends(get_provider)):
    """
    Health check: Verify provider connectivity.
    Useful for monitoring and debugging.
    """
    try:
        is_valid = provider.validate_credentials()
        return {
            "status": "healthy" if is_valid else "unhealthy",
            "provider": provider.__class__.__name__,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Provider unreachable: {str(e)}")


@router.post("/agents/launch-brief")
async def generate_launch_brief(
    client_profile: dict,
    provider = Depends(get_provider)
):
    """
    Example endpoint: Generate launch brief using approved client context.
    Same provider abstraction, different agent.
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
                }
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
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
