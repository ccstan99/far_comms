#!/usr/bin/env python

"""
Paper preprocessing utility for convert PDF research papers to markdown format.
Extracted from analyze_research.py to follow the same pattern as process_slides.
"""

import logging
import json
import re
import os
from pathlib import Path
from typing import Dict, Optional, Tuple
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Try importing PyMuPDF4LLM for better markdown extraction
try:
    import pymupdf4llm
    PYMUPDF4LLM_AVAILABLE = True
except ImportError:
    PYMUPDF4LLM_AVAILABLE = False
    logger.warning("PyMuPDF4LLM not available, falling back to standard extraction")


def process_paper(pdf_path: str, paper_title: str = None, authors: str = None) -> Dict[str, str]:
    """
    Process a research paper PDF into markdown format with metadata.
    
    Args:
        pdf_path: Path to the PDF file
        paper_title: Optional paper title override
        authors: Optional authors override
        
    Returns:
        Dict containing:
        - 'content': Cleaned markdown content
        - 'metadata': Paper metadata (title, authors, etc.)
        - 'raw_text': Raw extracted text
        - 'figures_info': Information about figures/tables
    """
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    logger.info(f"Processing paper: {pdf_path}")
    
    # Extract content using PyMuPDF4LLM if available, otherwise fallback
    if PYMUPDF4LLM_AVAILABLE:
        markdown_content = _extract_with_pymupdf4llm(pdf_path)
    else:
        markdown_content = _extract_with_standard_pymupdf(pdf_path)
    
    # Extract metadata
    metadata = _extract_pdf_metadata(pdf_path)
    
    # Override with provided values if given
    if paper_title:
        metadata['title'] = paper_title
    if authors:
        metadata['authors'] = authors
    
    # Filter main content (remove references, etc.)
    filtered_content = _filter_main_content(markdown_content)
    
    # Check for figures/tables
    has_visuals = _has_figures_or_tables(filtered_content)
    
    return {
        'content': filtered_content,
        'metadata': metadata,
        'raw_text': markdown_content,
        'figures_info': {'has_visuals': has_visuals}
    }


def _extract_with_pymupdf4llm(pdf_path: str) -> str:
    """Extract PDF content using PyMuPDF4LLM for better markdown formatting"""
    try:
        # Use PyMuPDF4LLM to get markdown-formatted text
        markdown_text = pymupdf4llm.to_markdown(
            pdf_path,
            page_chunks=False,  # Don't split into chunks
            write_images=False,  # Don't extract images
            embed_images=False   # Don't embed images
        )
        
        logger.info(f"PyMuPDF4LLM extraction: {len(markdown_text)} characters")
        return markdown_text
        
    except Exception as e:
        logger.error(f"PyMuPDF4LLM extraction failed: {e}")
        # Fallback to standard extraction
        return _extract_with_standard_pymupdf(pdf_path)


def _extract_with_standard_pymupdf(pdf_path: str) -> str:
    """Fallback PDF extraction using standard PyMuPDF"""
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            full_text += f"\n--- Page {page_num + 1} ---\n{text}\n"
        
        doc.close()
        logger.info(f"Standard PyMuPDF extraction: {len(full_text)} characters")
        return full_text
        
    except Exception as e:
        logger.error(f"Standard PDF extraction failed: {e}")
        raise


def _extract_pdf_metadata(pdf_path: str) -> Dict[str, str]:
    """Extract metadata from PDF file"""
    try:
        doc = fitz.open(pdf_path)
        metadata = doc.metadata
        doc.close()
        
        # Clean and structure metadata
        return {
            'title': metadata.get('title', '').strip() or Path(pdf_path).stem,
            'authors': metadata.get('author', '').strip(),
            'subject': metadata.get('subject', '').strip(),
            'creator': metadata.get('creator', '').strip(),
            'creation_date': metadata.get('creationDate', ''),
            'modification_date': metadata.get('modDate', ''),
            'file_path': str(pdf_path)
        }
        
    except Exception as e:
        logger.error(f"Failed to extract PDF metadata: {e}")
        return {
            'title': Path(pdf_path).stem,
            'authors': '',
            'subject': '',
            'creator': '',
            'creation_date': '',
            'modification_date': '',
            'file_path': str(pdf_path)
        }


def _filter_main_content(text_content: str) -> str:
    """Filter PDF content to focus on main paper, excluding bibliography, references, appendix"""
    lines = text_content.split('\n')
    
    # Common section headers that indicate end of main content
    end_markers = [
        r'^\s*references\s*$',
        r'^\s*bibliography\s*$', 
        r'^\s*appendix\s*$',
        r'^\s*appendix\s+[a-z]\s*$',
        r'^\s*acknowledgments?\s*$',
        r'^\s*acknowledgements?\s*$',
        r'^\s*supplementary\s+materials?\s*$',
        r'^\s*supplemental\s+materials?\s*$'
    ]
    
    # Find the first line that matches an end marker
    end_idx = len(lines)
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        for pattern in end_markers:
            if re.match(pattern, line_lower, re.IGNORECASE):
                end_idx = i
                logger.info(f"Filtering content at line {i}: '{line.strip()}'")
                break
        if end_idx < len(lines):
            break
    
    # Also look for numbered reference lists (e.g., "[1] Author, Title...")
    for i in range(end_idx):
        line = lines[i].strip()
        # Check if we hit a numbered reference list
        if re.match(r'^\[\d+\]\s+\w+', line) or re.match(r'^\d+\.\s+\w+.*\d{4}', line):
            # Verify this looks like a reference section by checking next few lines
            ref_count = 0
            for j in range(i, min(i+5, end_idx)):
                if re.match(r'^\[\d+\]|\^\d+\.', lines[j].strip()):
                    ref_count += 1
            if ref_count >= 2:  # Multiple numbered references
                end_idx = i
                logger.info(f"Found numbered references starting at line {i}")
                break
    
    # Return filtered content
    main_content = '\n'.join(lines[:end_idx])
    
    original_words = len(text_content.split())
    filtered_words = len(main_content.split())
    logger.info(f"Filtered content: {original_words} → {filtered_words} words ({filtered_words/original_words*100:.1f}% retained)")
    
    return main_content


def _has_figures_or_tables(text_content: str) -> bool:
    """Check if the paper contains figure or table references that would benefit from visual analysis"""
    figure_patterns = [
        r'\bfig\.?\s*\d+',
        r'\bfigure\s+\d+',
        r'\btable\s+\d+',
        r'\btab\.?\s*\d+',
        r'\bplot\s+\d+',
        r'\bgraph\s+\d+',
        r'\bchart\s+\d+',
        r'\bdiagram\s+\d+',
        r'see\s+figure',
        r'shown\s+in\s+figure',
        r'as\s+illustrated',
        r'algorithm\s+\d+'
    ]
    
    text_lower = text_content.lower()
    
    for pattern in figure_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    # Also check for common visual indicators
    visual_keywords = ['algorithm', 'flowchart', 'visualization', 'plot', 'graph', 'chart']
    for keyword in visual_keywords:
        if keyword in text_lower:
            return True
    
    return False


if __name__ == "__main__":
    """Command line interface for testing paper processing"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python paper_processor.py <pdf_path> [paper_title] [authors]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    paper_title = sys.argv[2] if len(sys.argv) > 2 else None
    authors = sys.argv[3] if len(sys.argv) > 3 else None
    
    try:
        result = process_paper(pdf_path, paper_title, authors)
        
        print("="*80)
        print("PAPER PROCESSING COMPLETE")
        print("="*80)
        print(f"Title: {result['metadata']['title']}")
        print(f"Authors: {result['metadata']['authors']}")
        print(f"Content length: {len(result['content'])} characters")
        print(f"Has figures/tables: {result['figures_info']['has_visuals']}")
        print("="*80)
        
    except Exception as e:
        print(f"Error processing paper: {e}")
        sys.exit(1)