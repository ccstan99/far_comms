#!/usr/bin/env python

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import (
    FunctionName, TalkRequest, ResearchRequest, ResearchAnalysisResponse, CodaIds
)
from far_comms.handlers.promote_talk import (
    run_promote_talk, 
    get_promote_talk_input,
    display_promote_talk_input
)
from far_comms.handlers.prepare_talk import (
    prepare_talk,
    get_input as get_prepare_talk_input, 
    display_input as display_prepare_talk_input
)
from far_comms.handlers.analyze_talk import (
    run_analyze_talk,
    get_analyze_talk_input,
    display_analyze_talk_input
)
from far_comms.handlers.analyze_research_handler import (
    run_analyze_research,
    get_analyze_research_input, 
    display_analyze_research_input
)
import uvicorn
import os
import json
import logging
from dotenv import load_dotenv
from far_comms.utils.project_paths import get_project_root, get_docs_dir, get_output_dir

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Suppress verbose logging from specific libraries
logging.getLogger('anthropic._base_client').setLevel(logging.WARNING)
logging.getLogger('anthropic').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('PIL.PngImagePlugin').setLevel(logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()
coda_headers = {'Authorization': f'Bearer {os.getenv("CODA_API_TOKEN")}'}

# Project directories
PROJECT_DIR = get_project_root()
DOCS_DIR = get_docs_dir()
OUTPUT_DIR = get_output_dir()

# Models imported from far_comms.models.requests

app = FastAPI()

@app.on_event("startup")
async def validate_environment():
    """Validate required environment variables on startup"""
    required_vars = {
        "CODA_API_TOKEN": "Coda API integration",
        "ANTHROPIC_API_KEY": "Claude model access"
    }
    
    optional_vars = {
        "ASSEMBLYAI_API_KEY": "YouTube transcript extraction (optional)"
    }
    
    missing_vars = []
    for var, purpose in required_vars.items():
        if not os.getenv(var):
            missing_vars.append(f"{var} (required for {purpose})")
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    # Check optional variables
    missing_optional = []
    for var, purpose in optional_vars.items():
        if not os.getenv(var):
            missing_optional.append(f"{var} (for {purpose})")
    
    if missing_optional:
        logger.warning(f"Optional environment variables not set: {', '.join(missing_optional)}")
    
    logger.info("Environment validation passed")

@app.get("/")
def home():
    return RedirectResponse(url="/docs")

@app.get("/prepare_event")
async def prepare_event(table_id: str, doc_id: str):
    """Prepare event endpoint - calls prepare_talk for each speaker in the table"""
    try:
        logger.info(f"Prepare event called - doc_id: {doc_id}, table_id: {table_id}")
        
        import json
        
        # Initialize Coda client
        coda_client = CodaClient()
        
        # Get all rows from the table
        table_data_str = coda_client.get_table(doc_id, table_id)
        table_data = json.loads(table_data_str)
        rows = table_data.get("rows", [])
        
        logger.info(f"Found {len(rows)} rows in table")
        
        if not rows:
            return {
                "status": "no_rows",
                "message": "No rows found in table"
            }
        
        # Process each row and track results
        successful_speakers = []
        skipped_speakers = []
        failed_speakers = []
        
        for row in rows:
            row_id = row.get("row_id")
            row_data = row.get("data", {})
            speaker_name = row_data.get("Speaker", "")
            
            if not speaker_name or not row_id:
                logger.warning(f"Skipping row {row_id} - missing speaker name or row_id")
                failed_speakers.append(f"{row_id or 'unknown'} (missing data)")
                continue
                
            logger.info(f"Processing speaker: {speaker_name}")
            
            # Create function_data for prepare_talk (needs speaker name and YouTube URL)
            yt_url = row_data.get("YT url", "")
            function_data = {
                "speaker": speaker_name,
                "yt_full_link": yt_url
            }
            
            # Create CodaIds for this row
            coda_ids = CodaIds(
                doc_id=doc_id,
                table_id=table_id,
                row_id=row_id
            )
            
            # Call prepare_talk for this speaker and handle structured results
            try:
                result = await prepare_talk(function_data, coda_ids)
                
                # Categorize based on prepare_talk's return status
                if result.get("status") == "success":
                    successful_speakers.append(f"{speaker_name}: {result.get('message', 'Success')}")
                elif result.get("status") == "skipped":
                    skipped_speakers.append(f"{speaker_name}: {result.get('message', 'Skipped')}")
                else:  # "failed" or any other status
                    failed_speakers.append(f"{speaker_name}: {result.get('message', 'Failed')}")
                
                # Add delay between speakers to avoid rate limits
                # import asyncio
                # await asyncio.sleep(2)  # Wait 2 seconds between speakers
                
            except Exception as e:
                logger.error(f"Failed to prepare {speaker_name}: {e}")
                failed_speakers.append(f"{speaker_name} (exception: {str(e)[:50]}...)")
        
        # Create detailed summary message
        summary_parts = []
        if successful_speakers:
            summary_parts.append(f"succeeded: {len(successful_speakers)}")
        if skipped_speakers:
            summary_parts.append(f"skipped: {len(skipped_speakers)}")
        if failed_speakers:
            summary_parts.append(f"failed: {len(failed_speakers)}")
        
        summary = f"Prepare event completed - {', '.join(summary_parts)}"
        
        return {
            "status": "success",
            "message": summary,
            "successful_speakers": successful_speakers,
            "skipped_speakers": skipped_speakers,
            "failed_speakers": failed_speakers,
            "total_rows": len(rows)
        }
        
    except Exception as e:
        logger.error(f"Prepare event error: {e}", exc_info=True)
        return {"error": f"Failed to prepare event: {e}"}

# Handler functions imported from far_comms.handlers

@app.post("/promote_talk")
async def promote_talk_endpoint(
    talk_request: TalkRequest,
    background_tasks: BackgroundTasks
):
    """HTTP endpoint for talk promotion - accepts TalkRequest JSON directly"""
    try:
        background_tasks.add_task(run_promote_talk, talk_request)
        
        return {
            "status": "In progress",
            "message": "Crew process will complete asynchronously",
            **talk_request.model_dump(exclude={"transcript"})
        }
        
    except Exception as e:
        return {"error": f"Failed to process talk request: {e}"}


@app.post(
    "/analyze_research",
    response_model=ResearchAnalysisResponse,
    summary="Analyze ML Research Paper",
    description="Analyze an ML research paper with PhD-level AI safety expertise using Claude 4.1 Opus. Saves results as Markdown file for human review. Accepts local file paths or URLs.",
    response_description="Detailed technical analysis saved as Markdown file, optimized for human review and subsequent LLM processing",
    tags=["Research Analysis"]
)
async def analyze_research_endpoint(research_request: ResearchRequest):
    """
    Analyze ML research paper with PhD-level AI safety technical expertise.
    
    This endpoint processes ML research papers and provides comprehensive analysis including:
    - Complete file extraction (PDF text, metadata, figures)
    - Structured markdown with headers and embedded figures
    - Distilled summary preserving researchers' terminology
    - Organized directory structure for easy access
    
    **Parameters:**
    - **pdf_path**: Local file path or URL to PDF (e.g., 'data/research/paper.pdf' or ArXiv URL)
    - **project_name**: Short name for directory structure (e.g., 'APE_eval', 'constitutional_ai')
    
    **Returns:**
    Comprehensive analysis with all outputs saved to output/research/{project_name}/
    - pdf.txt: Raw text extraction
    - pdf.json: Complete metadata
    - cleaned.md: Full structured markdown  
    - distilled.md: Bullet-point summary
    - figures/: All extracted images
    """
    try:
        # Convert to function_data format expected by handler
        function_data = {
            "pdf_path": research_request.pdf_path,
            "project_name": research_request.project_name
        }
        
        # Run analysis synchronously and return results
        result = await run_analyze_research(function_data, None)
        
        return result
        
    except Exception as e:
        logger.error(f"Error in analyze_research endpoint: {e}", exc_info=True)
        return {"error": f"Failed to process research analysis request: {e}"}


async def get_input(function_name: FunctionName, this_row: str, doc_id: str) -> tuple[CodaIds, any]:
    """Get input data for a specific function by fetching from Coda and parsing"""
    logger.info(f"Getting input for {function_name.value} - this_row: {this_row}, doc_id: {doc_id}")
    
    table_id, row_id = this_row.split('/')
    
    # Use CodaClient to get row data (TODO: optimize to fetch only needed fields)
    coda_client = CodaClient()
    try:
        row_data_str = coda_client.get_row(doc_id, table_id, row_id)
        row_data = json.loads(row_data_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Coda row data as JSON: {e}")
        raise ValueError(f"Invalid JSON response from Coda: {e}")
    except Exception as e:
        logger.error(f"Failed to fetch Coda row data: {e}")
        raise
    
    # Create Coda IDs object
    coda_ids = CodaIds(
        doc_id=doc_id,
        table_id=table_id,
        row_id=row_id
    )

    # Get function-specific input parser and parse only what's needed
    raw_data = row_data["data"]
    function_config = FUNCTION_REGISTRY[function_name]
    function_data = function_config["get_input"](raw_data)
    
    return coda_ids, function_data

# Function registry - maps function names to their input/display handlers and runners
FUNCTION_REGISTRY = {
    FunctionName.PROMOTE_TALK: {
        "runner": run_promote_talk,
        "get_input": get_promote_talk_input,
        "display_input": display_promote_talk_input
    },
    FunctionName.PREPARE_TALK: {
        "runner": prepare_talk,
        "get_input": get_prepare_talk_input,
        "display_input": display_prepare_talk_input
    },
    FunctionName.ANALYZE_TALK: {
        "runner": run_analyze_talk,
        "get_input": get_analyze_talk_input,
        "display_input": display_analyze_talk_input
    },
    FunctionName.PROMOTE_RESEARCH: {
        "runner": run_analyze_research,
        "get_input": get_analyze_research_input,
        "display_input": display_analyze_research_input
    }
    # Add new functions here as they're implemented
}

@app.api_route("/coda_webhook/{function_name}", methods=["GET"])
async def coda_webhook_endpoint(
    function_name: FunctionName,
    request: Request,
    background_tasks: BackgroundTasks,
    this_row: str = None,
    doc_id: str = None,
):
    """Generic Coda webhook - routes to different functions based on 'function_name' parameter"""
    method = request.method
    logger.info(f"Coda webhook hit - method: {method}, function_name: {function_name}")
    logger.debug(f"Params - this_row: {this_row}, doc_id: {doc_id}")
    
    # Handle POST with JSON body (Coda webhook)
    if method == "POST":
        try:
            json_data = await request.json()
            if "this_row" in json_data:
                this_row = json_data.get("this_row")
            if "doc_id" in json_data:
                doc_id = json_data.get("doc_id")
            logger.debug(f"Extracted from JSON body: this_row={this_row}, doc_id={doc_id}")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse webhook JSON body: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing webhook body: {e}")
    
    # Validate required params
    if not this_row or not doc_id or not function_name:
        return {"error": "Missing required parameters: this_row, doc_id, and function_name"}
    
    # Validate function exists in registry
    if function_name not in FUNCTION_REGISTRY:
        available = [fn.value for fn in FunctionName]
        return {"error": f"Unknown function_name: {function_name}. Available: {available}"}
    
    try:
        # Get function configuration from registry
        function_config = FUNCTION_REGISTRY[function_name]
        
        # Get input data for this specific function (fetches from Coda and parses)
        coda_ids, function_data = await get_input(function_name, this_row, doc_id)
        
        # Get display fields using the function's input display formatter
        display_input = function_config["display_input"](function_data)
        
        # Update Coda status quickly and use same data for response
        coda_client = CodaClient()
        status_updates = {
            "Webhook status": "In progress",
            "Webhook progress": "Starting crew workflow..."
        }
        coda_client.update_row(**coda_ids.model_dump(), column_updates=status_updates)
        
        # Prepare response data using the status updates + display_input
        response_data = {
            **status_updates,
            **display_input
        }
        runner = function_config["runner"]
        
        # Execute crew function in background with proper async handling
        def execute_crew():
            import asyncio
            logger.info(f"Starting {function_name.value} crew in background")
            
            try:
                # Run the crew function
                if asyncio.iscoroutinefunction(runner):
                    # Async function - run it properly
                    asyncio.run(runner(function_data, coda_ids))
                else:
                    # Sync function - call directly
                    runner(function_data, coda_ids)
                logger.info(f"Completed {function_name.value} crew successfully")
            except Exception as e:
                logger.error(f"Crew execution failed: {e}", exc_info=True)
        
        background_tasks.add_task(execute_crew)
        
        return response_data
            
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return {"error": f"Failed to process Coda webhook for {function_name}: {e}"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)