#!/usr/bin/env python

"""
Handler for analyze_research function - processes ML research papers with AI safety expertise.
"""

import logging
import json
from far_comms.models.requests import ResearchRequest, ResearchAnalysisOutput
from far_comms.analyze_research import analyze_research_paper

logger = logging.getLogger(__name__)

def get_analyze_research_input(raw_data: dict) -> dict:
    """Parse raw data for analyze_research function"""
    return {
        "pdf_path": raw_data.get("pdf_path", ""),
        "paper_title": raw_data.get("paper_title"),
        "authors": raw_data.get("authors")
    }

def display_analyze_research_input(function_data: dict) -> dict:
    """Format function input for display - exclude potentially long paths"""
    return {
        "pdf_path": function_data.get("pdf_path", ""),
        "paper_title": function_data.get("paper_title", "Not specified"),
        "authors": function_data.get("authors", "Not specified")
    }

async def run_analyze_research(function_data: dict, coda_ids=None) -> dict:
    """
    Analyze ML research paper with PhD-level AI safety expertise.
    
    Args:
        function_data: Dict with pdf_path, paper_title (optional), authors (optional)
        coda_ids: Not used for research analysis (no Coda integration)
        
    Returns:
        dict: {"status": "success|failed", "message": "details", "analysis": ResearchAnalysisOutput}
    """
    try:
        logger.info("Starting research paper analysis")
        
        pdf_path = function_data.get("pdf_path", "")
        paper_title = function_data.get("paper_title")
        authors = function_data.get("authors")
        
        if not pdf_path:
            logger.error("No PDF path provided")
            return {"status": "failed", "message": "PDF path is required", "analysis": None}
        
        logger.info(f"Analyzing research paper: {pdf_path}")
        if paper_title:
            logger.info(f"Paper title: {paper_title}")
        if authors:
            logger.info(f"Authors: {authors}")
        
        # Analyze the research paper
        analysis = analyze_research_paper(pdf_path, paper_title, authors)
        
        logger.info("Research paper analysis completed successfully")
        
        return {
            "status": "success", 
            "message": "Research analysis completed successfully",
            "analysis": analysis.model_dump()
        }
        
    except FileNotFoundError as e:
        logger.error(f"PDF file not found: {e}")
        return {"status": "failed", "message": f"PDF file not found: {str(e)}", "analysis": None}
    except ValueError as e:
        logger.error(f"Invalid input or API error: {e}")
        return {"status": "failed", "message": f"Analysis error: {str(e)}", "analysis": None}
    except Exception as e:
        logger.error(f"Unexpected error in research analysis: {e}", exc_info=True)
        return {"status": "failed", "message": f"Analysis failed: {str(e)}", "analysis": None}