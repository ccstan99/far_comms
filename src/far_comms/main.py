#!/usr/bin/env python

import requests
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from far_comms.crews.promote_talk_crew import PromoteTalkCrew
from far_comms.utils.coda_client import CodaClient, CodaIds
from pydantic import BaseModel, HttpUrl
import uvicorn
import os
import json
import logging
from dotenv import load_dotenv
from datetime import datetime
import asyncio
from enum import Enum
from far_comms.utils.project_paths import get_project_root, get_docs_dir, get_output_dir

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()
coda_headers = {'Authorization': f'Bearer {os.getenv("CODA_API_TOKEN")}'}

# Project directories
PROJECT_DIR = get_project_root()
DOCS_DIR = get_docs_dir()
OUTPUT_DIR = get_output_dir()

class FunctionName(str, Enum):
    """Available crew function names for Coda webhook"""
    PROMOTE_TALK = "promote_talk"
    PROMOTE_RESEARCH = "promote_research" 
    PROMOTE_EVENT = "promote_event"
    # Add more as they're created:

class TalkRequest(BaseModel):
    """Unified model for talk promotion - works for both API and Coda"""
    speaker: str
    title: str
    event: str
    affiliation: str
    yt_full_link: str | HttpUrl
    resource_url: str | HttpUrl | None = None
    transcript: str

class CodaWebhookRequest(BaseModel):
    thisRow: str
    docId: str
    speaker: str | None = None

class TalkPromotionOutput(BaseModel):
    """Output from the talk promotion crew - keys match Coda column names"""
    paragraph_ai: str  # "Paragraph (AI)" column
    hooks_ai: list[str]  # "Hooks (AI)" column - 5 hooks 
    li_content: str  # "LI content" column
    x_content: str  # "X content" column
    eval_notes: str  # Rubric breakdown and checklist with compliance notes

app = FastAPI()

@app.on_event("startup")
async def validate_environment():
    """Validate required environment variables on startup"""
    required_vars = {
        "CODA_API_TOKEN": "Coda API integration",
        "ANTHROPIC_API_KEY": "Claude model access"
    }
    
    missing_vars = []
    for var, purpose in required_vars.items():
        if not os.getenv(var):
            missing_vars.append(f"{var} (required for {purpose})")
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    logger.info("Environment validation passed")

@app.get("/")
def home():
    return RedirectResponse(url="/docs")

# Assembly functions removed - now handled by compliance_auditor_agent in the crew

async def run_promote_talk(talk_request: TalkRequest, coda_ids: CodaIds = None):
    """Run crew in background - accepts TalkRequest directly"""
    try:
        logger.info(f"Starting PromoteTalk crew for {talk_request.speaker}: {talk_request.title}")
        logger.debug(f"Input transcript length: {len(talk_request.transcript or '')}")
        
        # Load style guides
        docs_dir = get_docs_dir()
        style_shared = (docs_dir / "style_shared.md").read_text() if (docs_dir / "style_shared.md").exists() else ""
        style_li = (docs_dir / "style_li.md").read_text() if (docs_dir / "style_li.md").exists() else ""
        style_x = (docs_dir / "style_x.md").read_text() if (docs_dir / "style_x.md").exists() else ""
        
        # Lookup speaker's X handle for Twitter/X content attribution
        coda_client = CodaClient()
        speaker_x_handle = ""
        try:
            speaker_x_handle = coda_client.get_x_handle(talk_request.speaker)
            logger.info(f"Retrieved X handle for {talk_request.speaker}: {speaker_x_handle}")
        except Exception as e:
            logger.warning(f"X handle lookup failed for {talk_request.speaker}: {e}")
            speaker_x_handle = talk_request.speaker  # Fallback to speaker name
        
        # Convert TalkRequest to crew data format
        crew_data = {
            "transcript": talk_request.transcript or "",
            "speaker": talk_request.speaker or "",
            "speaker_x_handle": speaker_x_handle,
            "yt_full_link": str(talk_request.yt_full_link) if talk_request.yt_full_link else "",
            "resource_url": str(talk_request.resource_url) if talk_request.resource_url else "",
            "event_name": talk_request.event or "",
            "affiliation": talk_request.affiliation or "",
            # Style guide content
            "style_shared": style_shared,
            "style_li": style_li,
            "style_x": style_x
        }
        
        # Add Coda IDs if provided (for error reporting)
        if coda_ids:
            crew_data.update(coda_ids.model_dump())
            logger.debug(f"Added Coda IDs for error reporting: {coda_ids}")
        
        logger.debug(f"Final crew data keys: {list(crew_data.keys())}")
        logger.debug(f"Final transcript length being sent to crew: {len(crew_data.get('transcript', ''))}")
        
        # Run the crew and capture results
        result = PromoteTalkCrew().crew().kickoff(inputs=crew_data)
        logger.info("Crew completed successfully!")
        
        # Update Coda with final results if Coda IDs provided
        if coda_ids and result:
            coda_client = CodaClient()
            
            # Parse crew output - assuming result has the content we need
            # You may need to adjust these field names based on actual crew output structure
            try:
                # Extract structured data from crew result
                crew_output = result.raw if hasattr(result, 'raw') else str(result)
                
                # Parse the output if it's JSON, otherwise use as string
                try:
                    parsed_output = json.loads(crew_output) if isinstance(crew_output, str) else crew_output
                except (json.JSONDecodeError, TypeError):
                    parsed_output = {"content": crew_output}
                
                logger.info(f"Parsed crew output keys: {list(parsed_output.keys()) if isinstance(parsed_output, dict) else 'Not a dict'}")
                
                # Extract from new clean structure - Coda fields at top level
                paragraph_summary = parsed_output.get("paragraph_ai", "")
                # Skip hooks_ai - raw JSON is unreadable in Coda interface
                li_content = parsed_output.get("li_content", "")
                x_content = parsed_output.get("x_content", "")
                
                # X handle attribution is now handled by the X writer agent during content creation
                
                # Notes section contains all intermediate work
                notes = parsed_output.get("notes", {})
                publication_decision = notes.get("publication_decision", "NEEDS_REVISION")
                
                logger.info(f"Publication decision: {publication_decision}")
                
                # Map publication decision to Coda status
                status_mapping = {
                    "APPROVED": "Done",
                    "NEEDS_REVISION": "Needs review", 
                    "REJECTED": "Error",
                    "NEEDS_MANUAL_REVIEW": "Needs review"
                }
                coda_status = status_mapping.get(publication_decision, "Needs review")
                logger.info(f"Setting Coda status: {coda_status}")
                
                # Prepare final updates for Coda columns
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": {
                        "Summaries status": coda_status,
                        "Progress": json.dumps(parsed_output, indent=2),
                        # Map assembled content to Coda columns:
                        "Paragraph (AI)": paragraph_summary,
                        # Skip "Hooks (AI)" - raw JSON is unreadable in Coda
                        "LI content": li_content,
                        "X content": x_content,
                        "Eval notes": notes.get("eval_notes", "")
                    }
                }]
                
                logger.info(f"Updating Coda columns: {list(updates[0]['updates'].keys())}")
                
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Coda update result: {result}")
                logger.info(f"Updated Coda with crew results")
                
            except Exception as update_error:
                logger.error(f"Failed to update Coda with results: {update_error}")
                # Mark as error and put details in Progress
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": {
                        "Summaries status": "Error",
                        "Progress": f"Update error: {str(update_error)}"
                    }
                }]
                coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
        
    except Exception as e:
        logger.error(f"Background crew error: {e}", exc_info=True)
        # If crew fails, update status via CodaClient
        if coda_ids:
            coda_client = CodaClient()
            updates = [{
                "row_id": coda_ids.row_id,
                "updates": {
                    "Summaries status": "Error",
                    "Progress": f"Crew error: {str(e)}"
                }
            }]
            coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
            logger.info(f"Updated Coda row with error status")

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

async def get_coda_data(this_row: str, doc_id: str) -> tuple[CodaIds, TalkRequest]:
    """Extract data from Coda row and return Coda IDs + TalkRequest"""
    logger.info(f"Extracting data from Coda - this_row: {this_row}, doc_id: {doc_id}")
    
    table_id, row_id = this_row.split('/')
    
    # Use CodaClient to get row data
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
    
    # Extract talk data from the row
    talk_data_dict = row_data["data"]
    
    # Map to TalkRequest fields (adjust field names as needed)
    talk_request_data = {
        "speaker": talk_data_dict.get("Speaker", ""),
        "title": talk_data_dict.get("Title", ""),
        "event": talk_data_dict.get("Event", ""),
        "affiliation": talk_data_dict.get("Affiliation", ""),
        "yt_full_link": talk_data_dict.get("YT full link", ""),
        "transcript": talk_data_dict.get("Transcript", ""),
        "resource_url": talk_data_dict.get("Resource URL", ""),
    }
    
    talk_data = TalkRequest(**talk_request_data)
    logger.info(f"Successfully validated Coda data: {talk_data.speaker} - {talk_data.title}")
    
    # Create Coda IDs object
    coda_ids = CodaIds(
        doc_id=doc_id,
        table_id=table_id,
        row_id=row_id
    )

    return coda_ids, talk_data

@app.api_route("/coda_webhook/{function_name}", methods=["GET", "POST"])
async def coda_webhook_endpoint(
    function_name: FunctionName,
    request: Request,
    this_row: str = None,
    doc_id: str = None
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
    
    # Map function names to crew runner functions
    function_runners = {
        FunctionName.PROMOTE_TALK: run_promote_talk,
        # Add more functions as they're created:
        # FunctionName.PROMOTE_RESEARCH: run_promote_research,
        # FunctionName.PROMOTE_EVENT: run_promote_event,
    }
    
    if function_name not in function_runners:
        available = [fn.value for fn in FunctionName]
        return {"error": f"Unknown function_name: {function_name}. Available: {available}"}
    
    try:
        # Extract data from Coda
        coda_ids, talk_data = await get_coda_data(this_row, doc_id)
        
        # Prepare response data
        response_data = {
            "status": "In progress",
            "message": f"{function_name.value} crew process will complete asynchronously",
            **talk_data.model_dump(exclude={"transcript"})
        }
        
        # Update Coda row with status and progress in single batch call
        coda_client = CodaClient()
        updates = [{
            "row_id": coda_ids.row_id,
            "updates": {
                "Summaries status": "In progress",
                "Progress": "Starting crew workflow..."
            }
        }]
        coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
        
        # Start the crew function directly
        import asyncio
        runner = function_runners[function_name]
        asyncio.create_task(runner(talk_data, coda_ids))
        
        return response_data
            
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return {"error": f"Failed to process Coda webhook for {function_name}: {e}"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)