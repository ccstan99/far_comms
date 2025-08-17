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

# Function configurations for run_event functionality
RUN_EVENT_CONFIG = {
    "prepare_talk": {
        "execution_mode": "row_based",
        "description": "Process slides and transcripts for talks"
    },
    "promote_talk": {
        "execution_mode": "row_based", 
        "description": "Generate social media content for talks"
    },
    "promote_research": {
        "execution_mode": "row_based",
        "description": "Analyze research papers and generate insights"
    },
    # Future functions can be added here:
    # "recap": {"execution_mode": "event_based", "description": "Generate event recap"}
    # "blog": {"execution_mode": "event_based", "description": "Generate blog post"}  
    # "announcement": {"execution_mode": "event_based", "description": "Generate event announcement"}
}

def execute_run_event(func_name: str, table_id: str, doc_id: str, row_ids: list = None):
    """Generic background function that processes table rows with specified function"""
    try:
        import json
        import asyncio
        
        # Validate function name exists in both registries
        if func_name not in RUN_EVENT_CONFIG:
            raise ValueError(f"Unknown function '{func_name}'. Available: {list(RUN_EVENT_CONFIG.keys())}")
        
        # Convert string function name to FunctionName enum for FUNCTION_REGISTRY lookup
        func_name_enum = None
        for enum_val in FUNCTION_REGISTRY:
            if enum_val.value == func_name:
                func_name_enum = enum_val
                break
        
        if not func_name_enum:
            raise ValueError(f"Function '{func_name}' not found in FUNCTION_REGISTRY")
        
        # Get configuration from both registries
        run_config = RUN_EVENT_CONFIG[func_name]
        func_config = FUNCTION_REGISTRY[func_name_enum]
        
        handler = func_config["runner"]
        input_parser = func_config["get_input"]
        execution_mode = run_config["execution_mode"]
        
        logger.info(f"Starting run_event: {func_name} ({execution_mode})")
        
        # Initialize Coda client
        coda_client = CodaClient()
        
        # For row_based functions: iterate through table rows
        if execution_mode == "row_based":
            # Get all rows from the table
            table_data_str = coda_client.get_table(doc_id, table_id)
            table_data = json.loads(table_data_str)
            rows = table_data.get("rows", [])
            
            # Filter to specific row_ids if provided
            if row_ids:
                rows = [row for row in rows if row.get("row_id") in row_ids]
                logger.info(f"Filtering to {len(rows)} specified rows: {row_ids}")
            
            logger.info(f"Found {len(rows)} rows to process with {func_name}")
            
            if not rows:
                logger.warning("No rows found to process")
                return {"status": "completed", "message": "No rows to process"}
            
            # Process each row and track results
            successful_rows = []
            skipped_rows = []
            failed_rows = []
            
            for row in rows:
                row_id = row.get("row_id")
                row_data = row.get("data", {})
                speaker_name = row_data.get("Speaker", "")
                
                if not speaker_name or not row_id:
                    logger.warning(f"Skipping row {row_id} - missing speaker name or row_id")
                    failed_rows.append(f"{row_id or 'unknown'} (missing data)")
                    continue
                    
                logger.info(f"Processing {func_name} for speaker: {speaker_name}")
                
                # Parse input data using function-specific parser
                function_data = input_parser(row_data)
                
                # Create CodaIds for this row
                coda_ids = CodaIds(
                    doc_id=doc_id,
                    table_id=table_id,
                    row_id=row_id
                )
                
                # Call handler for this row (synchronously)
                try:
                    result = asyncio.run(handler(function_data, coda_ids))
                    
                    # Categorize based on handler's return status
                    if result and result.get("status") == "success":
                        successful_rows.append(f"{speaker_name}: {result.get('message', 'Success')}")
                    elif result and result.get("status") == "skipped":
                        skipped_rows.append(f"{speaker_name}: {result.get('message', 'Skipped')}")
                    else:  # "failed" or any other status
                        failed_rows.append(f"{speaker_name}: {result.get('message', 'Failed') if result else 'No result'}")
                    
                except Exception as e:
                    logger.error(f"Failed to run {func_name} for {speaker_name}: {e}")
                    failed_rows.append(f"{speaker_name} (exception: {str(e)[:50]}...)")
            
            # Create final summary
            summary_parts = []
            if successful_rows:
                summary_parts.append(f"succeeded: {len(successful_rows)}")
            if skipped_rows:
                summary_parts.append(f"skipped: {len(skipped_rows)}")
            if failed_rows:
                summary_parts.append(f"failed: {len(failed_rows)}")
            
            summary = f"{func_name} event completed - {', '.join(summary_parts)}"
            logger.info(f"Background run_event finished: {summary}")
            
            return {
                "status": "completed",
                "message": summary,
                "successful": len(successful_rows),
                "skipped": len(skipped_rows),
                "failed": len(failed_rows)
            }
        
        # For event_based functions: single function call with table metadata
        elif execution_mode == "event_based":
            # Future implementation for recap, blog, announcement functions
            # These don't iterate through rows but work with overall event data
            logger.info(f"Event-based execution for {func_name} not yet implemented")
            return {"status": "not_implemented", "message": f"Event-based execution for {func_name} coming soon"}
        
        else:
            raise ValueError(f"Unknown execution mode: {execution_mode}")
            
    except Exception as e:
        logger.error(f"Background run_event error: {e}", exc_info=True)
        return {"status": "failed", "message": f"Error: {str(e)}"}


@app.get("/run_event/{func_name}")
async def run_event(
    func_name: str, 
    table_id: str, 
    doc_id: str, 
    background_tasks: BackgroundTasks,
    row_ids: str = None
):
    """Generic run event endpoint - launches background processing with specified function
    
    Args:
        func_name: Function to run (prepare_talk, promote_talk, etc.)
        table_id: Coda table ID
        doc_id: Coda document ID  
        row_ids: Optional comma-separated list of specific row IDs to process
    """
    try:
        # Validate function name
        if func_name not in RUN_EVENT_CONFIG:
            available_functions = list(RUN_EVENT_CONFIG.keys())
            return {
                "error": f"Unknown function '{func_name}'. Available functions: {available_functions}"
            }
        
        run_config = RUN_EVENT_CONFIG[func_name]
        description = run_config["description"]
        execution_mode = run_config["execution_mode"]
        
        logger.info(f"Run event called - func_name: {func_name}, doc_id: {doc_id}, table_id: {table_id}")
        
        # Parse row_ids if provided
        parsed_row_ids = None
        if row_ids:
            parsed_row_ids = [rid.strip() for rid in row_ids.split(",") if rid.strip()]
            logger.info(f"Processing specific rows: {parsed_row_ids}")
        
        # Launch background processing using FastAPI BackgroundTasks
        background_tasks.add_task(
            execute_run_event, 
            func_name, 
            table_id, 
            doc_id, 
            parsed_row_ids
        )
        
        # Return immediately with status
        message = f"{func_name} event started. {description}."
        if parsed_row_ids:
            message += f" Processing {len(parsed_row_ids)} specific rows."
        else:
            message += " Processing all rows in background."
            
        return {
            "status": "in_progress", 
            "message": message,
            "function": func_name,
            "execution_mode": execution_mode,
            "doc_id": doc_id,
            "table_id": table_id,
            "row_ids": parsed_row_ids
        }
        
    except Exception as e:
        logger.error(f"Run event error: {e}", exc_info=True)
        return {"error": f"Failed to start {func_name} event: {e}"}



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