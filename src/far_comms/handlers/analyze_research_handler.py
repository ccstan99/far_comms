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

def _save_analysis_to_files(analysis: ResearchAnalysisOutput, pdf_path: str, paper_title: str = None, authors: str = None) -> dict:
    """Save analysis results to Markdown file (primary format for human review)"""
    try:
        # Create outputs directory
        from far_comms.utils.project_paths import get_output_dir
        output_dir = get_output_dir()
        output_dir.mkdir(exist_ok=True)
        
        # Generate filename
        title_for_filename = paper_title or Path(pdf_path).stem
        sanitized_title = _sanitize_filename(title_for_filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Handle duplicate filenames (check markdown first as primary format)
        base_filename = sanitized_title
        counter = 1
        while (output_dir / f"{sanitized_title}.md").exists():
            sanitized_title = f"{base_filename}_{counter}"
            counter += 1
        
        md_path = output_dir / f"{sanitized_title}.md"
        
        # Save Markdown file (primary format for human review)
        md_content = f"""# ML Research Paper Analysis
        
## Metadata
- **Paper Title**: {paper_title or 'Not provided'}
- **Authors**: {authors or 'Not provided'}
- **PDF Path**: {pdf_path}
- **Analysis Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Technical Analysis

### Core Contribution
{analysis.core_contribution}

### Methodology
{analysis.methodology}

### Key Results
{analysis.key_results}

### Technical Novelty
{analysis.technical_novelty}

## AI Safety & Alignment Context

### Safety Implications
{analysis.safety_implications}

### Risk Assessment
{analysis.risk_assessment}

### Alignment Relevance
{analysis.alignment_relevance}

## Research Quality & Significance

### Experimental Rigor
{analysis.experimental_rigor}

### Significance Rating
{analysis.significance_rating}

### Future Directions
{analysis.future_directions}

## Practical Applications

### Real-world Applications
{analysis.real_world_applications}

### Implementation Challenges
{analysis.implementation_challenges}

## Academic Context

### Related Work Analysis
{analysis.related_work_analysis}

### Citation-worthy Claims
"""
        
        for i, claim in enumerate(analysis.citation_worthy_claims, 1):
            md_content += f"{i}. {claim}\n"
        
        md_content += "\n## Communication & Framing\n\n### Research Framing for Different Audiences\n"
        
        for i, framing in enumerate(analysis.research_framing, 1):
            md_content += f"{i}. {framing}\n"
        
        md_content += "\n---\n*Analysis generated with Claude 4.1 Opus - PhD-level AI safety expertise*\n"
        
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Analysis saved to {md_path}")
        
        return {
            "markdown_path": str(md_path),
            "filename": sanitized_title
        }
        
    except Exception as e:
        logger.error(f"Error saving analysis files: {e}")
        return {
            "error": f"Failed to save files: {str(e)}"
        }

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
        
        # Save results to files
        file_info = _save_analysis_to_files(analysis, pdf_path, paper_title, authors)
        
        logger.info("Research paper analysis completed successfully")
        
        response = {
            "status": "success", 
            "message": "Research analysis completed successfully",
            "analysis": analysis.model_dump()
        }
        
        # Add file save information
        if "error" not in file_info:
            response["files_saved"] = file_info
            response["message"] += f" - Results saved to {file_info['filename']}.md"
        else:
            logger.warning(f"File saving failed: {file_info['error']}")
        
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