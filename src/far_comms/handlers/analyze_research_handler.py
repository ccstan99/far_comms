#!/usr/bin/env python

"""
Handler for analyze_research function - processes ML research papers with AI safety expertise.
"""

import logging
import json
import os
import re
from datetime import datetime
from pathlib import Path
from far_comms.models.requests import ResearchRequest, ResearchAnalysisOutput
from far_comms.analyze_research import analyze_research_paper

logger = logging.getLogger(__name__)

def _sanitize_filename(title: str, max_length: int = 100) -> str:
    """Sanitize paper title for use as filename"""
    if not title:
        return "untitled_paper"
    
    # Remove/replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', title)
    sanitized = re.sub(r'[^\w\s\-_\.]', '', sanitized)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = sanitized.strip('_').strip('.')
    
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip('_')
    
    return sanitized or "untitled_paper"

# File saving is now handled by analyze_research_paper function

def get_analyze_research_input(raw_data: dict) -> dict:
    """Parse raw data for analyze_research function"""
    return {
        "pdf_path": raw_data.get("pdf_path", ""),
        "project_name": raw_data.get("project_name", "")
    }

def display_analyze_research_input(function_data: dict) -> dict:
    """Format function input for display - exclude potentially long paths"""
    return {
        "pdf_path": function_data.get("pdf_path", ""),
        "project_name": function_data.get("project_name", "Not specified")
    }

async def run_analyze_research(function_data: dict, coda_ids=None) -> dict:
    """
    Analyze ML research paper with PhD-level AI safety expertise.
    
    Args:
        function_data: Dict with pdf_path, project_name
        coda_ids: Not used for research analysis (no Coda integration)
        
    Returns:
        dict: {"status": "success|failed", "message": "details", "analysis": ResearchAnalysisOutput}
    """
    try:
        logger.info("Starting research paper analysis")
        
        pdf_path = function_data.get("pdf_path", "")
        project_name = function_data.get("project_name", "")
        
        if not pdf_path:
            logger.error("No PDF path provided")
            return {"status": "failed", "message": "PDF path is required", "analysis": None}
        
        if not project_name:
            logger.error("No project name provided")
            return {"status": "failed", "message": "Project name is required", "analysis": None}
        
        logger.info(f"Analyzing research paper: {pdf_path}")
        logger.info(f"Project name: {project_name}")
        
        # Analyze the research paper (using project_name for directory structure)
        analysis = analyze_research_paper(pdf_path, paper_title=project_name)
        
        # Save results to files (now handled by analyze_research_paper function)
        logger.info("Research paper analysis completed successfully")
        
        response = {
            "status": "success", 
            "message": "Research analysis completed successfully with 4 outputs (raw text, metadata JSON, cleaned markdown, distilled markdown)",
            "analysis": analysis.model_dump()
        }
        
        return response
        
    except FileNotFoundError as e:
        logger.error(f"PDF file not found: {e}")
        return {"status": "failed", "message": f"PDF file not found: {str(e)}", "analysis": None}
    except ValueError as e:
        logger.error(f"Invalid input or API error: {e}")
        return {"status": "failed", "message": f"Analysis error: {str(e)}", "analysis": None}
    except Exception as e:
        logger.error(f"Unexpected error in research analysis: {e}", exc_info=True)
        return {"status": "failed", "message": f"Analysis failed: {str(e)}", "analysis": None}