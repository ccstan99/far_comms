#!/usr/bin/env python

import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pptx import Presentation
    PYTHON_PPTX_AVAILABLE = True
except ImportError:
    PYTHON_PPTX_AVAILABLE = False

logger = logging.getLogger(__name__)




def extract_pdf_content(file_path: str) -> Dict[str, Any]:
    """
    Extract text content from a PDF file using PyMuPDF
    
    Args:
        file_path: Path to the PDF file
    
    Returns:
        Dictionary containing extracted content and metadata
    """
    if not PYMUPDF_AVAILABLE:
        return {
            "error": "PyMuPDF not available. Install with: pip install PyMuPDF",
            "content": "",
            "slides": [],
            "page_count": 0
        }
    
    try:
        doc = fitz.open(file_path)
        slides = []
        all_text = []
        page_count = len(doc)  # Store this before closing
        
        for page_num in range(page_count):
            page = doc.load_page(page_num)
            text = page.get_text()
            
            # Always include pages to maintain structure
            slides.append({
                "page": page_num + 1,
                "content": text.strip() if text.strip() else f"[PAGE {page_num + 1} - NO TEXT EXTRACTED]"
            })
            
            if text.strip():
                all_text.append(text.strip())
        
        doc.close()
        
        full_content = "\n\n---PAGE BREAK---\n\n".join(all_text)
        
        return {
            "file_type": "pdf",
            "file_name": Path(file_path).name,
            "page_count": page_count,
            "slides": slides,
            "content": full_content,
            "success": True
        }
        
    except Exception as e:
        logger.error(f"Error extracting PDF content from {file_path}: {e}")
        return {
            "error": str(e),
            "content": "",
            "slides": [],
            "page_count": 0,
            "success": False
        }


def extract_pptx_content(file_path: str) -> Dict[str, Any]:
    """
    Extract text content from a PowerPoint file using python-pptx
    
    Args:
        file_path: Path to the PPTX file
    
    Returns:
        Dictionary containing extracted content and metadata
    """
    if not PYTHON_PPTX_AVAILABLE:
        return {
            "error": "python-pptx not available. Install with: pip install python-pptx",
            "content": "",
            "slides": [],
            "slide_count": 0
        }
    
    try:
        prs = Presentation(file_path)
        slides = []
        all_text = []
        
        for slide_num, slide in enumerate(prs.slides):
            slide_text = []
            
            # Extract text from all shapes
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_text.append(shape.text.strip())
            
            if slide_text:  # Only include slides with content
                slide_content = "\n".join(slide_text)
                slides.append({
                    "slide": slide_num + 1,
                    "content": slide_content
                })
                all_text.append(slide_content)
        
        full_content = "\n\n---SLIDE BREAK---\n\n".join(all_text)
        
        return {
            "file_type": "pptx",
            "file_name": Path(file_path).name,
            "slide_count": len(prs.slides),
            "slides": slides,
            "content": full_content,
            "success": True
        }
        
    except Exception as e:
        logger.error(f"Error extracting PPTX content from {file_path}: {e}")
        return {
            "error": str(e),
            "content": "",
            "slides": [],
            "slide_count": 0,
            "success": False
        }


def extract_slide_content(file_path: str) -> Dict[str, Any]:
    """
    Extract content from presentation files (PDF or PPTX)
    
    Args:
        file_path: Path to the presentation file
    
    Returns:
        Dictionary containing extracted content and metadata
    """
    if not os.path.exists(file_path):
        return {
            "error": f"File not found: {file_path}",
            "content": "",
            "slides": [],
            "success": False
        }
    
    file_path = str(Path(file_path).resolve())
    file_ext = Path(file_path).suffix.lower()
    
    if file_ext == '.pdf':
        return extract_pdf_content(file_path)
    elif file_ext in ['.pptx', '.ppt']:
        return extract_pptx_content(file_path)
    else:
        return {
            "error": f"Unsupported file type: {file_ext}. Supported: .pdf, .pptx, .ppt",
            "content": "",
            "slides": [],
            "success": False
        }


def get_slide_summary(content_dict: Dict[str, Any]) -> str:
    """
    Get a concise summary of extracted slide content
    
    Args:
        content_dict: Result from extract_slide_content()
    
    Returns:
        Human-readable summary string
    """
    if not content_dict.get("success"):
        return f"Extraction failed: {content_dict.get('error', 'Unknown error')}"
    
    file_type = content_dict.get("file_type", "unknown")
    file_name = content_dict.get("file_name", "unknown")
    
    if file_type == "pdf":
        count = content_dict.get("page_count", 0)
        unit = "pages"
    else:
        count = content_dict.get("slide_count", 0)
        unit = "slides"
    
    content_length = len(content_dict.get("content", ""))
    
    return f"Extracted from {file_name}: {count} {unit}, {content_length} characters"


# Example usage and testing
if __name__ == "__main__":
    # Test with the provided file
    test_file = "/Users/cheng2/Desktop/agents/far_comms/data/slides/11_50_Xiaoyuan Yi-ValueCompass_updated.pptx.pdf"
    
    print("Testing slide extraction...")
    result = extract_slide_content(test_file)
    
    print(f"Success: {result.get('success')}")
    print(get_slide_summary(result))
    
    if result.get("success"):
        print(f"\nFirst 500 characters of content:")
        print(result.get("content", "")[:500])
        print("\n" + "="*50)
        
        print(f"\nFirst slide/page content:")
        slides = result.get("slides", [])
        if slides:
            print(slides[0].get("content", "")[:300])
    else:
        print(f"Error: {result.get('error')}")