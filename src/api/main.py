"""
Vantdge Backend API

FastAPI server exposing Vantdge agents and tools for the frontend.
"""
import os
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lazy imports to avoid loading heavy dependencies at startup
_agents_loaded = False
_agent_instances = {}


def get_settings():
    """Get settings from environment variables."""
    from src.utils.config import get_settings as _get_settings
    return _get_settings()


def load_agents():
    """Lazy load agents when first needed."""
    global _agents_loaded, _agent_instances
    if _agents_loaded:
        return _agent_instances
    
    try:
        settings = get_settings()
        
        # Import agents
        from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent
        from src.tools.pubmed import PubMedAPI
        from src.tools.web_search import WebSearchTool
        from anthropic import Anthropic
        
        # Initialize shared components
        anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
        pubmed_api = PubMedAPI(api_key=getattr(settings, 'pubmed_api_key', None))
        web_search = WebSearchTool(api_key=settings.tavily_api_key) if settings.tavily_api_key else None
        
        # Initialize case series agent
        database_url = getattr(settings, 'drug_database_url', None) or getattr(settings, 'disease_landscape_url', None)
        _agent_instances['case_series'] = DrugRepurposingCaseSeriesAgent(
            anthropic_api_key=settings.anthropic_api_key,
            database_url=database_url,
            tavily_api_key=getattr(settings, 'tavily_api_key', None),
            pubmed_email='api@vantdge.com'
        )
        
        _agents_loaded = True
        logger.info("Agents loaded successfully")
        
    except Exception as e:
        logger.error(f"Failed to load agents: {e}")
        raise
    
    return _agent_instances


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Vantdge API starting up...")
    yield
    logger.info("Vantdge API shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Vantdge API",
    description="AI-Powered Biopharma Intelligence Platform Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class HealthResponse(BaseModel):
    status: str
    version: str


class DrugAnalysisRequest(BaseModel):
    drug_name: str = Field(..., description="Name of the drug to analyze")
    max_papers: int = Field(default=50, description="Maximum papers to analyze")
    include_web_search: bool = Field(default=True, description="Include web search results")


class DrugAnalysisResponse(BaseModel):
    drug_name: str
    status: str
    opportunities_found: int
    message: str


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - health check."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.post("/api/v1/analyze/drug", response_model=DrugAnalysisResponse)
async def analyze_drug(request: DrugAnalysisRequest):
    """
    Analyze a drug for repurposing opportunities.
    
    This endpoint triggers the DrugRepurposingCaseSeriesAgent to find
    off-label use cases and repurposing opportunities.
    """
    try:
        agents = load_agents()
        agent = agents.get('case_series')
        
        if not agent:
            raise HTTPException(status_code=503, detail="Case series agent not available")
        
        # Run analysis (this can take a while)
        results = agent.analyze_drug(
            drug_name=request.drug_name,
            max_papers=request.max_papers,
            include_web_search=request.include_web_search
        )
        
        opportunities = results.get('opportunities', [])
        
        return DrugAnalysisResponse(
            drug_name=request.drug_name,
            status="completed",
            opportunities_found=len(opportunities),
            message=f"Analysis complete. Found {len(opportunities)} repurposing opportunities."
        )
        
    except Exception as e:
        logger.error(f"Drug analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/status")
async def get_status():
    """Get API status and configuration."""
    settings = get_settings()
    return {
        "status": "running",
        "anthropic_configured": bool(settings.anthropic_api_key),
        "tavily_configured": bool(getattr(settings, 'tavily_api_key', None)),
        "database_configured": bool(getattr(settings, 'drug_database_url', None))
    }


# ============================================================================
# Prompt Management Endpoints
# ============================================================================

class PromptTemplate(BaseModel):
    name: str
    category: str
    content: str
    path: str


class PromptUpdateRequest(BaseModel):
    content: str = Field(..., description="New template content")


@app.get("/api/v1/prompts/categories")
async def list_prompt_categories():
    """List all prompt template categories."""
    from src.prompts import get_prompt_manager
    from pathlib import Path

    pm = get_prompt_manager()
    templates_dir = Path(pm.templates_dir)

    categories = []
    for item in templates_dir.iterdir():
        if item.is_dir() and not item.name.startswith('_'):
            categories.append({
                "name": item.name,
                "template_count": len(list(item.rglob("*.j2")))
            })

    return {"categories": sorted(categories, key=lambda x: x["name"])}


@app.get("/api/v1/prompts")
async def list_prompts(category: Optional[str] = None):
    """List all prompt templates, optionally filtered by category."""
    from src.prompts import get_prompt_manager
    from pathlib import Path

    pm = get_prompt_manager()
    templates_dir = Path(pm.templates_dir)

    templates = []

    if category:
        search_dir = templates_dir / category
        if not search_dir.exists():
            raise HTTPException(status_code=404, detail=f"Category not found: {category}")
        template_files = search_dir.rglob("*.j2")
    else:
        template_files = templates_dir.rglob("*.j2")

    for template_path in template_files:
        rel_path = template_path.relative_to(templates_dir)
        # Skip partials
        if '_partials' in str(rel_path):
            continue

        # Extract category from path
        parts = rel_path.parts
        cat = parts[0] if len(parts) > 1 else "root"

        templates.append({
            "name": template_path.stem,
            "category": cat,
            "path": str(rel_path).replace('\\', '/'),
            "full_path": str(template_path)
        })

    return {"templates": sorted(templates, key=lambda x: (x["category"], x["name"]))}


@app.get("/api/v1/prompts/{category}/{template_name}")
async def get_prompt(category: str, template_name: str):
    """Get a specific prompt template content."""
    from src.prompts import get_prompt_manager
    from pathlib import Path

    pm = get_prompt_manager()
    templates_dir = Path(pm.templates_dir)

    # Try with and without .j2 extension
    if not template_name.endswith('.j2'):
        template_name = f"{template_name}.j2"

    template_path = templates_dir / category / template_name

    if not template_path.exists():
        raise HTTPException(status_code=404, detail=f"Template not found: {category}/{template_name}")

    content = template_path.read_text(encoding='utf-8')

    return {
        "name": template_path.stem,
        "category": category,
        "path": f"{category}/{template_name}",
        "content": content
    }


@app.put("/api/v1/prompts/{category}/{template_name}")
async def update_prompt(category: str, template_name: str, request: PromptUpdateRequest):
    """Update a prompt template content."""
    from src.prompts import get_prompt_manager
    from pathlib import Path
    import shutil
    from datetime import datetime

    pm = get_prompt_manager()
    templates_dir = Path(pm.templates_dir)

    # Try with and without .j2 extension
    if not template_name.endswith('.j2'):
        template_name = f"{template_name}.j2"

    template_path = templates_dir / category / template_name

    if not template_path.exists():
        raise HTTPException(status_code=404, detail=f"Template not found: {category}/{template_name}")

    # Create backup before modifying
    backup_dir = templates_dir / "_backups" / category
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{template_path.stem}_{timestamp}.j2.bak"
    shutil.copy2(template_path, backup_path)

    # Write new content
    template_path.write_text(request.content, encoding='utf-8')

    # Clear cache in PromptManager
    if pm._cache is not None:
        pm._cache.clear()

    logger.info(f"Updated template: {category}/{template_name}")

    return {
        "status": "updated",
        "path": f"{category}/{template_name}",
        "backup_path": str(backup_path)
    }


@app.get("/api/v1/prompts/partials/{category}")
async def list_partials(category: str):
    """List partial templates for a category."""
    from src.prompts import get_prompt_manager
    from pathlib import Path

    pm = get_prompt_manager()
    templates_dir = Path(pm.templates_dir)

    partials_dir = templates_dir / category / "_partials"

    if not partials_dir.exists():
        return {"partials": []}

    partials = []
    for partial_path in partials_dir.glob("*.j2"):
        partials.append({
            "name": partial_path.stem,
            "path": f"{category}/_partials/{partial_path.name}",
            "content": partial_path.read_text(encoding='utf-8')
        })

    return {"partials": partials}

