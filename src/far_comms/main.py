#!/usr/bin/env python

import requests
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from far_comms.crews.promote_talk_crew import FarCommsCrew
from far_comms.tools.coda_tool import CodaTool, CodaIds
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

@app.get("/")
def home():
    return RedirectResponse(url="/docs")

async def run_promote_talk(talk_request: TalkRequest, coda_ids: CodaIds = None):
    """Run crew in background - accepts TalkRequest directly"""
    try:
        logger.info(f"Starting FarComms crew for {talk_request.speaker}: {talk_request.title}")
        
        # Load style guides
        docs_dir = get_docs_dir()
        style_shared = (docs_dir / "style_shared.md").read_text() if (docs_dir / "style_shared.md").exists() else ""
        style_li = (docs_dir / "style_li.md").read_text() if (docs_dir / "style_li.md").exists() else ""
        style_x = (docs_dir / "style_x.md").read_text() if (docs_dir / "style_x.md").exists() else ""
        
        # Convert TalkRequest to crew data format
        crew_data = {
            "transcript": talk_request.transcript or "",
            "speaker": talk_request.speaker or "",
            "video_url": str(talk_request.yt_full_link) if talk_request.yt_full_link else "",
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
        
        # Run the crew and capture results
        result = FarCommsCrew().crew().kickoff(inputs=crew_data)
        logger.info("Crew completed successfully!")
        
        # Update Coda with final results if Coda IDs provided
        if coda_ids and result:
            coda_tool = CodaTool()
            
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
                logger.debug(f"hooks_ai type: {type(parsed_output.get('hooks_ai'))}, value: {parsed_output.get('hooks_ai')}")
                
                # Handle hooks_ai properly - could be string or list
                hooks_ai = parsed_output.get("hooks_ai", [])
                if isinstance(hooks_ai, str):
                    # If it's a string, assume it's already formatted or split by newlines
                    hooks_formatted = hooks_ai
                elif isinstance(hooks_ai, list):
                    # If it's a list, format as bullet points
                    hooks_formatted = "\n".join([f"- {hook}" for hook in hooks_ai])
                else:
                    hooks_formatted = ""
                
                # Fix template variables in x_content
                x_content = parsed_output.get("x_content", "")
                if x_content:
                    x_content = x_content.replace("{video_url}", str(talk_request.yt_full_link) if talk_request.yt_full_link else "")
                    x_content = x_content.replace("{resource_url}", str(talk_request.resource_url) if talk_request.resource_url else "")
                
                logger.info(f"X content length: {len(x_content)}, preview: {x_content[:100]}...")
                
                # Prepare updates for Coda columns
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": {
                        "Summaries status": "Done",
                        "Results": json.dumps(parsed_output, indent=2),
                        # Map crew outputs to Coda columns - adjust field names as needed:
                        "Paragraph (AI)": parsed_output.get("paragraph_ai", ""),
                        "Hooks (AI)": hooks_formatted,
                        "LI content": parsed_output.get("li_content", ""),
                        "X content": x_content,
                        "Eval notes": parsed_output.get("eval_notes", "")
                    }
                }]
                
                coda_tool.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Successfully updated Coda with crew results")
                
            except Exception as update_error:
                logger.error(f"Failed to update Coda with results: {update_error}")
                # Mark as error and put details in Results
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": {
                        "Summaries status": "Error",
                        "Results": f"Update error: {str(update_error)}"
                    }
                }]
                coda_tool.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
        
    except Exception as e:
        logger.error(f"Background crew error: {e}", exc_info=True)
        # If crew fails, update status via CodaTool
        if coda_ids:
            coda_tool = CodaTool()
            updates = [{
                "row_id": coda_ids.row_id,
                "updates": {
                    "Summaries status": "Error",
                    "Results": f"Crew error: {str(e)}"
                }
            }]
            coda_tool.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
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
    
    # Use CodaTool to get row data
    coda_tool = CodaTool()
    row_data_str = coda_tool.get_row(doc_id, table_id, row_id)
    row_data = json.loads(row_data_str)
    
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
        except:
            pass
    
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
        
        # Update Coda row with status and results in single batch call
        coda_tool = CodaTool()
        updates = [{
            "row_id": coda_ids.row_id,
            "updates": {
                "Summaries status": "In progress",
                "Results": str(response_data)
            }
        }]
        coda_tool.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
        
        # Start the crew function directly
        import asyncio
        runner = function_runners[function_name]
        asyncio.create_task(runner(talk_data, coda_ids))
        
        return response_data
            
    except Exception as e:
        return {"error": f"Failed to process Coda webhook for {function_name}: {e}"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)