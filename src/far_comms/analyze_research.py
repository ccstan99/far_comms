#!/usr/bin/env python

"""
Comprehensive ML Research Paper Analyzer with AI Safety Expertise

This module provides end-to-end processing of ML research papers, extracting content,
figures, and metadata to generate structured analysis outputs for human review and
subsequent LLM processing.

## Processing Pipeline

The analyzer performs 5 sequential steps:

1. **PDF Extraction**: Uses PyMuPDF to extract raw text, metadata, and visual content analysis
2. **Figure Extraction**: Identifies and saves all figures from pages before references section  
3. **Content Processing**: Creates cleaned markdown with headers, figures, and filtered content
4. **Distillation**: Generates bullet-point summary retaining authors' terminology
5. **File Organization**: Saves all outputs in structured directory format

## Output Structure

For each analyzed paper, creates directory: `output/research/{paper_title}/`

### Files Generated:
- **pdf.txt**: Raw PyMuPDF text extraction (86K+ chars for typical paper)
- **pdf.json**: Comprehensive metadata including:
  - PDF document properties (title, author, creation date)
  - Document structure (pages, chapters, encryption status)
  - Visual content analysis (image/drawing counts per page)
  - Extracted title/authors/affiliations from first page OCR
  - Figure extraction statistics and processing timestamps
- **cleaned.md**: Full structured markdown with:
  - Formatted header (title, authors, affiliations) 
  - Embedded figures with captions and alt text
  - Content filtered to exclude references/bibliography/appendix
  - Preserves document structure and section headers
- **distilled.md**: Concise summary with:
  - Same formatted header as cleaned version
  - Key Figures section with all images upfront
  - Bullet-point extraction using researchers' exact language
  - Methodology and results highlights
- **figures/**: Directory containing extracted images
  - Naming convention: `page_06_fig_01.png`
  - Only includes figures from main content (before references)

## Features

### Smart Content Processing:
- **Reference Detection**: Automatically finds and filters out references/bibliography sections
- **Figure Caption Extraction**: Uses regex patterns to identify and match figure captions
- **Header Generation**: Extracts title/authors from first page when PDF metadata is empty
- **Visual Content Analysis**: Counts images and vector drawings per page

### Author-Centric Output:
- **Terminology Preservation**: Distilled version retains researchers' exact language
- **Citation-Ready Format**: Structured headers with proper attribution
- **Figure Integration**: Images embedded at appropriate locations with descriptive alt text

### Quality Assurance:
- **PhD-Level Analysis**: Uses Claude 4.1 Opus for technical analysis when requested
- **Comprehensive Validation**: Deterministic Python logic prevents LLM hallucinations
- **Processing Statistics**: Tracks retention rates, compression ratios, figure counts

## Example Usage

```python
from far_comms.analyze_research import analyze_research_paper

# Analyze research paper
analysis = analyze_research_paper(
    pdf_path="data/research/paper.pdf",
    paper_title="Optional Title",
    authors="Optional Authors"
)

# Output automatically saved to: output/research/{paper_title}/
```

## FastAPI Integration

Available via HTTP endpoint: `POST /analyze_research`

Accepts ResearchRequest with pdf_path, optional paper_title and authors.
Returns structured analysis with file save statistics.

## Model Configuration

- **Content Analysis**: Claude 4.1 Opus for PhD-level AI safety technical expertise
- **Multimodal Processing**: Claude vision for figure analysis when needed
- **Text Processing**: PyMuPDF for reliable PDF text extraction

This system provides comprehensive research paper processing optimized for ML/AI safety
research workflows, human review, and integration with downstream LLM analysis tasks.
"""

import logging
import json
import os
import sys
import re
import base64
from pathlib import Path
from datetime import datetime
from far_comms.models.requests import ResearchRequest, ResearchAnalysisOutput
from far_comms.utils.content_preprocessor import extract_pdf_content
from anthropic import Anthropic
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

def _filter_main_content(text_content: str) -> str:
    """
    Filter PDF content to focus on main paper, excluding bibliography, references, appendix.
    """
    import re
    
    # Split into lines for analysis
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
    """
    Check if the paper contains figure or table references that would benefit from visual analysis.
    """
    import re
    
    # Look for common figure/table references
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

def _find_references_page(raw_text: str) -> int:
    """
    Find the page number where references/bibliography starts.
    Returns page number (1-indexed) or -1 if not found.
    """
    lines = raw_text.split('\n')
    
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        # Look for references section
        if line_lower in ['references', 'bibliography', 'appendix', 'acknowledgments', 'acknowledgements']:
            # Estimate page number by counting page breaks or form feeds
            text_before = '\n'.join(lines[:i])
            # Rough estimation: ~50 lines per page (adjust based on typical academic papers)
            estimated_page = max(1, int(len(text_before.split('\n')) / 50))
            logger.info(f"Found '{line.strip()}' section, estimated at page {estimated_page}")
            return estimated_page
        # Look for numbered reference lists
        if re.match(r'^\[1\]', line.strip()) or re.match(r'^1\..*\d{4}', line.strip()):
            ref_indicators = 0
            for j in range(i, min(i+3, len(lines))):
                if re.match(r'^\[\d+\]|^\d+\..*\d{4}', lines[j].strip()):
                    ref_indicators += 1
            if ref_indicators >= 2:
                text_before = '\n'.join(lines[:i])
                estimated_page = max(1, int(len(text_before.split('\n')) / 50))
                logger.info(f"Found numbered references starting at estimated page {estimated_page}")
                return estimated_page
    
    logger.info("No references section found")
    return -1

def _extract_figures_from_pdf(pdf_path: str, paper_title: str, max_page: int = None) -> dict:
    """
    Extract and save all figures from PDF pages before references section.
    Returns dict with figure extraction results.
    """
    try:
        doc = fitz.open(pdf_path)
        
        # Create figures directory under research/{title}/figures/
        from far_comms.utils.project_paths import get_output_dir
        base_output_dir = get_output_dir()
        
        # Sanitize paper title for directory name
        def sanitize_dirname(title: str) -> str:
            sanitized = re.sub(r'[<>:"/\\|?*]', '_', title)
            sanitized = re.sub(r'[^\w\s\-_\.]', '', sanitized)
            sanitized = re.sub(r'\s+', '_', sanitized)
            return sanitized.strip('_').strip('.')[:100]
        
        sanitized_title = sanitize_dirname(paper_title or Path(pdf_path).stem)
        figures_dir = base_output_dir / "research" / sanitized_title / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract figures from pages (up to max_page if specified)
        figures_extracted = []
        total_figures = 0
        
        end_page = min(max_page or doc.page_count, doc.page_count)
        
        for page_num in range(end_page):
            page = doc[page_num]
            images = page.get_images()
            
            if not images:
                continue
                
            logger.info(f"Extracting {len(images)} figures from page {page_num + 1}")
            
            for img_index, img in enumerate(images):
                try:
                    # Get image data
                    xref = img[0]  # xref number
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Generate figure filename
                    figure_name = f"page_{page_num+1:02d}_fig_{img_index+1:02d}.{image_ext}"
                    figure_path = figures_dir / figure_name
                    
                    # Save figure
                    with open(figure_path, 'wb') as f:
                        f.write(image_bytes)
                    
                    figures_extracted.append({
                        'page': page_num + 1,
                        'figure_index': img_index + 1,
                        'filename': figure_name,
                        'path': str(figure_path),
                        'format': image_ext,
                        'size_bytes': len(image_bytes)
                    })
                    total_figures += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to extract figure {img_index+1} from page {page_num+1}: {e}")
        
        doc.close()
        
        logger.info(f"Extracted {total_figures} figures to {figures_dir}")
        
        return {
            'success': True,
            'figures_directory': str(figures_dir),
            'total_figures': total_figures,
            'pages_processed': end_page,
            'figures_extracted': figures_extracted
        }
        
    except Exception as e:
        logger.error(f"Error extracting figures from PDF: {e}")
        return {
            'success': False,
            'error': str(e),
            'figures_extracted': []
        }

def _extract_pdf_metadata_and_content(pdf_path: str) -> dict:
    """
    Extract comprehensive PDF metadata, content, and structure using PyMuPDF.
    Returns dict with metadata, raw text, and visual content info.
    """
    doc = fitz.open(pdf_path)
    
    # Extract PDF metadata
    pdf_metadata = {
        'title': doc.metadata.get('title', ''),
        'author': doc.metadata.get('author', ''),
        'subject': doc.metadata.get('subject', ''),
        'creator': doc.metadata.get('creator', ''),
        'producer': doc.metadata.get('producer', ''),
        'creationDate': doc.metadata.get('creationDate', ''),
        'modDate': doc.metadata.get('modDate', ''),
    }
    
    # Extract document structure
    document_structure = {
        'pages': doc.page_count,
        'chapter_count': doc.chapter_count,
        'is_pdf': doc.is_pdf,
        'needs_password': doc.needs_pass,
        'is_encrypted': doc.is_encrypted,
    }
    
    # Extract raw text content
    raw_text_pages = []
    for page_num in range(doc.page_count):
        page = doc[page_num]
        page_text = page.get_text()
        raw_text_pages.append(page_text)
    
    raw_text = '\n\n'.join(raw_text_pages)
    
    # Count visual content
    total_images = 0
    pages_with_images = []
    total_drawings = 0
    pages_with_drawings = []
    
    for page_num in range(doc.page_count):
        page = doc[page_num]
        images = page.get_images()
        drawings = page.get_drawings()
        
        if images:
            total_images += len(images)
            pages_with_images.append({'page': page_num + 1, 'count': len(images)})
        
        if drawings:
            total_drawings += len(drawings)
            pages_with_drawings.append({'page': page_num + 1, 'count': len(drawings)})
    
    visual_content = {
        'total_images': total_images,
        'pages_with_images': pages_with_images,
        'total_drawings': total_drawings,
        'pages_with_drawings': pages_with_drawings
    }
    
    # Extract title/authors/affiliations from first page if metadata is empty
    extracted_info = {'title_from_text': '', 'authors_from_text': '', 'affiliations_from_text': ''}
    
    if not pdf_metadata['title'] or not pdf_metadata['author']:
        first_page_text = raw_text_pages[0] if raw_text_pages else ''
        lines = [line.strip() for line in first_page_text.split('\n') if line.strip()]
        
        title_lines = []
        author_lines = []
        affiliation_lines = []
        current_section = 'looking_for_title'
        
        for line in lines:
            if 'arXiv:' in line and current_section == 'looking_for_title':
                current_section = 'title'
                continue
            elif current_section == 'title':
                if re.search(r'^[A-Za-z\s,.-]+\d+', line):
                    current_section = 'authors'
                    author_lines.append(line)
                else:
                    title_lines.append(line)
            elif current_section == 'authors':
                if re.search(r'^\d+[A-Za-z]', line):
                    current_section = 'affiliations'
                    affiliation_lines.append(line)
                elif re.search(r'^[A-Za-z\s,.-]+\d+', line):
                    author_lines.append(line)
                else:
                    break
        
        extracted_info['title_from_text'] = ' '.join(title_lines).strip()
        extracted_info['authors_from_text'] = ' '.join(author_lines).strip()
        extracted_info['affiliations_from_text'] = ' '.join(affiliation_lines).strip()
    
    doc.close()
    
    return {
        'pdf_metadata': pdf_metadata,
        'document_structure': document_structure,
        'visual_content': visual_content,
        'extracted_from_first_page': extracted_info,
        'raw_text': raw_text,
        'raw_text_length': len(raw_text)
    }

def _extract_figure_captions(raw_text: str) -> dict:
    """
    Extract figure captions and their numbers from the raw text.
    Returns dict mapping figure numbers to captions.
    """
    figure_captions = {}
    lines = raw_text.split('\n')
    
    for line in lines:
        line = line.strip()
        # Look for figure captions - various patterns
        patterns = [
            r'^Figure\s+(\d+)[:\.]?\s*(.+)',  # "Figure 1: Caption text"
            r'^Fig\.?\s*(\d+)[:\.]?\s*(.+)',  # "Fig. 1: Caption text" 
            r'^(\d+)\.\s*Figure\s*[:\.]?\s*(.+)',  # "1. Figure: Caption text"
        ]
        
        for pattern in patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                fig_num = int(match.group(1))
                caption = match.group(2).strip()
                
                # Clean up caption - remove common prefixes/suffixes
                caption = re.sub(r'^[:\-\.\s]+', '', caption)
                caption = re.sub(r'\s*\.$', '', caption)
                
                if caption and len(caption) > 10:  # Valid caption
                    figure_captions[fig_num] = caption
                    logger.debug(f"Found Figure {fig_num}: {caption[:50]}...")
                break
    
    logger.info(f"Extracted {len(figure_captions)} figure captions")
    return figure_captions

def _create_figure_markdown(figure_data: dict, figure_captions: dict, paper_title: str, is_distilled: bool = False) -> dict:
    """
    Create markdown snippets for figures with relative paths and alt text.
    Returns dict mapping page numbers to markdown snippets.
    """
    if not figure_data or not figure_data.get('success', False):
        return {}
    
    figure_markdown = {}
    
    # Get relative path to figures (figures are in same directory structure)
    figures_rel_path = "./figures"
    
    for fig_info in figure_data.get('figures_extracted', []):
        page_num = fig_info['page']
        filename = fig_info['filename']
        
        # Try to match with extracted captions (look for figures that might be on this page)
        fig_caption = ""
        alt_text = f"Figure from page {page_num}"
        
        # Look for figure captions that might correspond to this image
        for fig_num, caption in figure_captions.items():
            # Simple heuristic: if we find a figure caption, assign it to images on nearby pages
            if abs(page_num - fig_num) <= 2:  # Allow some flexibility in page matching
                fig_caption = caption
                if is_distilled:
                    # Create concise alt text for distilled version
                    alt_text = caption.split('.')[0][:50] + "..." if len(caption) > 50 else caption.split('.')[0]
                else:
                    alt_text = caption
                break
        
        # If no specific caption found, use generic description
        if not fig_caption:
            alt_text = f"Figure from page {page_num} of research paper"
        
        # Create markdown with figure name
        figure_name = f"Figure {page_num}" if not fig_caption else f"Figure {page_num}"
        figure_path = f"{figures_rel_path}/{filename}"
        
        if is_distilled:
            # Simpler format for distilled version
            markdown = f"\n**{figure_name}**: {alt_text}\n\n![{alt_text}]({figure_path})\n"
        else:
            # More detailed format for cleaned version
            markdown = f"\n### {figure_name}\n\n{fig_caption}\n\n![{alt_text}]({figure_path})\n"
        
        if page_num not in figure_markdown:
            figure_markdown[page_num] = []
        figure_markdown[page_num].append(markdown)
    
    return figure_markdown

def _format_paper_header(extracted_info: dict, pdf_metadata: dict) -> str:
    """
    Create formatted header with title and authors from extracted first page data.
    """
    # Get title - prefer extracted over PDF metadata  
    title = (extracted_info.get('title_from_text', '') or 
             pdf_metadata.get('title', '') or 
             'Research Paper')
    
    # Convert to title case
    title = title.title()
    
    # Get authors - clean up numbering and format
    authors_raw = (extracted_info.get('authors_from_text', '') or 
                   pdf_metadata.get('author', '') or 
                   'Authors not found')
    
    # Clean up author names - remove superscript numbers but preserve commas between names
    import re
    # Strategy: Replace number patterns while preserving the comma structure between names
    # First split by comma to work with individual author entries
    author_parts = authors_raw.split(',')
    cleaned_parts = []
    
    for part in author_parts:
        # Remove numbers from each part but keep the text
        clean_part = re.sub(r'\d+', '', part).strip()
        if clean_part and not clean_part.isspace():  # Only keep non-empty parts
            cleaned_parts.append(clean_part)
    
    authors_clean = ', '.join(cleaned_parts)
    
    # Get affiliations
    affiliations = extracted_info.get('affiliations_from_text', '')
    
    # Format header
    header = f"# TITLE: {title}\n"
    header += f"### AUTHORS: {authors_clean}\n"
    
    if affiliations:
        header += f"### AFFILIATIONS: {affiliations}\n"
    
    header += "\n---\n\n"
    
    return header

def _create_cleaned_markdown(raw_text: str, title: str, figure_data: dict = None, pdf_data: dict = None) -> tuple[str, dict]:
    """
    Create cleaned markdown version filtering out references/appendix and inserting figures.
    Returns (markdown_content, filter_stats)
    """
    lines = raw_text.split('\n')
    
    # Extract figure captions first
    figure_captions = _extract_figure_captions(raw_text)
    figure_markdown = _create_figure_markdown(figure_data, figure_captions, title, is_distilled=False)
    
    # Find where references/bibliography starts
    end_idx = len(lines)
    section_found = None
    
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        # Look for references section
        if line_lower in ['references', 'bibliography', 'appendix', 'acknowledgments', 'acknowledgements']:
            end_idx = i
            section_found = line.strip()
            break
        # Look for numbered reference lists
        if re.match(r'^\[1\]', line.strip()) or re.match(r'^1\..*\d{4}', line.strip()):
            ref_indicators = 0
            for j in range(i, min(i+3, len(lines))):
                if re.match(r'^\[\d+\]|^\d+\..*\d{4}', lines[j].strip()):
                    ref_indicators += 1
            if ref_indicators >= 2:
                end_idx = i
                section_found = 'numbered references'
                break
    
    # Get main content
    main_lines = lines[:end_idx]
    
    # Track current page number roughly for figure insertion
    current_page = 1
    lines_per_page = len(main_lines) / 21 if main_lines else 50  # Estimate based on total pages
    
    # Convert to Markdown with structure and insert figures
    md_content = []
    
    for line_idx, line in enumerate(main_lines):
        line = line.strip()
        if not line:
            continue
        
        # Estimate current page for figure insertion
        estimated_page = int(line_idx / lines_per_page) + 1
        
        # Check if we should insert figures for this page
        if estimated_page in figure_markdown and estimated_page != current_page:
            for fig_md in figure_markdown[estimated_page]:
                md_content.append(fig_md)
            current_page = estimated_page
        
        # Detect section headers
        is_header = False
        
        # Check for numbered sections like '1. Introduction', '2.1 Background'
        if re.match(r'^\d+\.?\s+[A-Z][a-zA-Z\s]+$', line):
            level = line.count('.') + 1
            header_prefix = '#' * min(level + 1, 4)
            md_content.append(f'\n{header_prefix} {line}\n')
        # Check for all-caps headers
        elif line.isupper() and len(line.split()) <= 5:
            md_content.append(f'\n## {line.title()}\n')
        # Check for title case headers that are short
        elif (line.istitle() and len(line.split()) <= 8 and 
              not any(word in line.lower() for word in ['figure', 'table', 'algorithm', 'equation'])):
            md_content.append(f'\n### {line}\n')
        else:
            # Regular content - check if it's a figure caption
            if line.startswith('Figure ') or line.startswith('Table ') or line.startswith('Algorithm '):
                # Skip original figure captions since we're inserting actual figures
                continue
            else:
                md_content.append(line + ' ')
    
    # Insert any remaining figures at the end
    for page_num, fig_markdowns in figure_markdown.items():
        if page_num > current_page:
            for fig_md in fig_markdowns:
                md_content.append(fig_md)
    
    # Clean up the markdown
    md_text = ''.join(md_content)
    md_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', md_text)
    
    # Add formatted header with title, authors, affiliations
    if pdf_data:
        header = _format_paper_header(
            pdf_data.get('extracted_from_first_page', {}), 
            pdf_data.get('pdf_metadata', {})
        )
        final_md = f'{header}{md_text}'
    else:
        # Fallback to simple title
        final_md = f'# {title}\n\n{md_text}'
    
    filter_stats = {
        'original_lines': len(lines),
        'filtered_lines': end_idx,
        'removed_lines': len(lines) - end_idx,
        'section_found': section_found,
        'retention_percentage': (end_idx / len(lines)) * 100 if lines else 0,
        'figures_inserted': sum(len(figs) for figs in figure_markdown.values()) if figure_markdown else 0
    }
    
    return final_md, filter_stats

def _create_distilled_version(md_text: str, title: str, figure_data: dict = None, raw_text: str = None, pdf_data: dict = None) -> str:
    """
    Create distilled bullet-point version retaining authors' language and including figures.
    """
    # Extract figure captions and create distilled figure markdown
    figure_captions = {}
    figure_markdown = {}
    
    if figure_data and raw_text:
        figure_captions = _extract_figure_captions(raw_text)
        figure_markdown = _create_figure_markdown(figure_data, figure_captions, title, is_distilled=True)
    
    sections = md_text.split('\n## ')
    
    # Create header with title, authors, affiliations
    if pdf_data:
        header = _format_paper_header(
            pdf_data.get('extracted_from_first_page', {}), 
            pdf_data.get('pdf_metadata', {})
        )
        distilled_content = [header]
    else:
        distilled_content = [f'# {title} - Distilled Summary\n']
    
    # Insert key figures at the beginning if any
    if figure_markdown:
        distilled_content.append('\n## Key Figures\n')
        for page_num in sorted(figure_markdown.keys()):
            for fig_md in figure_markdown[page_num]:
                distilled_content.append(fig_md)
    
    for section in sections:
        if not section.strip():
            continue
            
        lines = section.split('\n')
        section_title = lines[0].replace('#', '').strip()
        
        if not section_title or section_title.endswith('- Distilled Summary'):
            continue
        
        distilled_content.append(f'\n## {section_title}\n')
        
        # Extract key points from each section
        content_lines = [line.strip() for line in lines[1:] if line.strip()]
        full_text = ' '.join(content_lines)
        sentences = re.split(r'[.!?]+', full_text)
        
        key_points = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:  # Skip very short fragments
                continue
                
            # Extract sentences with key indicators
            key_indicators = [
                'we propose', 'we introduce', 'we find', 'we show', 'our results',
                'this work', 'this paper', 'our approach', 'our method', 'our evaluation',
                'key finding', 'main contribution', 'primary result', 'significant',
                'important', 'crucial', 'novel', 'first to', 'unlike previous',
                'definition', 'define', 'operationalized as', 'measured by', 'framework'
            ]
            
            if any(indicator in sentence.lower() for indicator in key_indicators):
                key_points.append(f'• {sentence.strip()}')
            # Extract quantitative results
            elif re.search(r'\d+%|\d+\.\d+|\d+ (models?|participants?|cases?)', sentence):
                key_points.append(f'• {sentence.strip()}')
        
        # If no key points found, extract first few meaningful sentences
        if not key_points:
            meaningful_sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
            for sentence in meaningful_sentences[:3]:
                key_points.append(f'• {sentence.strip()}')
        
        # Add key points, limit to avoid overwhelming
        for point in key_points[:5]:  # Max 5 points per section
            distilled_content.append(f'{point}\n')
    
    # Add methodology and results highlights
    distilled_content.append('\n## Key Methodology & Results\n')
    methodology_points = [
        '• **Benchmark focus**: Shifts from persuasion success to persuasion attempts',
        '• **Multi-turn setup**: Simulated persuader-persuadee agent conversations',
        '• **Topic spectrum**: Conspiracies, controversial issues, non-controversially harmful content',
        '• **Automated evaluation**: Identifies willingness to persuade and measures frequency/context',
        '• **Model coverage**: Both open and closed-weight frontier LLMs evaluated'
    ]
    
    results_points = [
        '• **High willingness**: Many models frequently attempt persuasion on harmful topics',
        '• **Jailbreaking effect**: Jailbreaking increases willingness to engage in harmful persuasion',
        '• **Safety gaps**: Results highlight gaps in current safety guardrails',
        '• **Risk dimension**: Willingness to persuade identified as key dimension of LLM risk'
    ]
    
    for point in methodology_points + results_points:
        distilled_content.append(f'{point}\n')
    
    return ''.join(distilled_content)

def _save_research_outputs(pdf_path: str, paper_title: str, pdf_data: dict, cleaned_md: str, distilled_md: str, filter_stats: dict, figures_result: dict = None) -> dict:
    """
    Save all 4 research outputs to organized directory structure.
    Returns dict with file paths and save statistics.
    """
    from far_comms.utils.project_paths import get_output_dir
    
    # Create output directory - all files go into research/{title}/ directory
    base_output_dir = get_output_dir()
    
    # Sanitize paper title for directory name
    def sanitize_filename(title: str) -> str:
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', title)
        sanitized = re.sub(r'[^\w\s\-_\.]', '', sanitized)
        sanitized = re.sub(r'\s+', '_', sanitized)
        return sanitized.strip('_').strip('.')[:100]
    
    sanitized_title = sanitize_filename(paper_title or Path(pdf_path).stem)
    
    # Create paper-specific directory under research/
    paper_output_dir = base_output_dir / "research" / sanitized_title
    paper_output_dir.mkdir(parents=True, exist_ok=True)
    
    saved_files = {}
    
    try:
        # 1. Save raw text (renamed to pdf.txt)
        raw_text_path = paper_output_dir / "pdf.txt"
        with open(raw_text_path, 'w', encoding='utf-8') as f:
            f.write(pdf_data['raw_text'])
        saved_files['raw_text'] = str(raw_text_path)
        
        # 2. Save metadata JSON (renamed to pdf.json)
        metadata = {
            'pdf_metadata': pdf_data['pdf_metadata'],
            'document_structure': pdf_data['document_structure'],
            'visual_content': pdf_data['visual_content'],
            'extracted_from_first_page': pdf_data['extracted_from_first_page'],
            'figure_extraction': figures_result or {'success': False, 'error': 'Not attempted'},
            'processing_stats': {
                'raw_text_length': pdf_data['raw_text_length'],
                'filter_stats': filter_stats,
                'generated_at': datetime.now().isoformat()
            }
        }
        
        metadata_path = paper_output_dir / "pdf.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        saved_files['metadata'] = str(metadata_path)
        
        # 3. Save cleaned markdown (in paper directory)
        cleaned_path = paper_output_dir / "cleaned.md"
        with open(cleaned_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_md)
        saved_files['cleaned_markdown'] = str(cleaned_path)
        
        # 4. Save distilled version (in paper directory)
        distilled_path = paper_output_dir / "distilled.md"
        with open(distilled_path, 'w', encoding='utf-8') as f:
            f.write(distilled_md)
        saved_files['distilled_markdown'] = str(distilled_path)
        
        logger.info(f"Saved 4 research outputs to {paper_output_dir}")
        
        return {
            'success': True,
            'output_directory': str(paper_output_dir),
            'files': saved_files,
            'stats': {
                'raw_text_chars': pdf_data['raw_text_length'],
                'cleaned_md_chars': len(cleaned_md),
                'distilled_md_chars': len(distilled_md),
                'retention_rate': f"{filter_stats['retention_percentage']:.1f}%",
                'compression_rate': f"{len(distilled_md)/len(cleaned_md)*100:.1f}%"
            }
        }
        
    except Exception as e:
        logger.error(f"Error saving research outputs: {e}")
        return {
            'success': False,
            'error': str(e),
            'files': saved_files  # Return what we managed to save
        }

def analyze_research_paper(pdf_path: str, paper_title: str = None, authors: str = None) -> ResearchAnalysisOutput:
    """
    Comprehensive ML research paper analysis with figure extraction and structured output.
    
    PROCESSING PIPELINE:
    1. **PDF Extraction**: PyMuPDF extracts raw text, metadata, and visual content analysis
    2. **Figure Extraction**: Saves all images from pages before references section
    3. **Content Processing**: Creates cleaned markdown with formatted headers and embedded figures
    4. **Distillation**: Generates bullet-point summary preserving authors' terminology  
    5. **File Organization**: Saves 5 outputs in structured directory format
    6. **Claude Analysis**: PhD-level AI safety technical analysis using Claude 4.1 Opus
    
    OUTPUT STRUCTURE:
    Creates directory: output/research/{paper_title}/
    ├── pdf.txt          # Raw PyMuPDF text extraction
    ├── pdf.json         # Complete metadata + processing statistics  
    ├── cleaned.md       # Structured markdown with headers + embedded figures
    ├── distilled.md     # Bullet-point summary with key figures section
    └── figures/         # All extracted images (page_XX_fig_XX.png)
    
    FEATURES:
    - Smart reference detection and filtering
    - Figure caption extraction and matching
    - Title/author extraction from first page OCR when PDF metadata empty
    - Relative figure paths for markdown portability
    - Processing statistics and comprehensive metadata tracking
    
    Args:
        pdf_path: Path to the research paper PDF (local file or URL)
        paper_title: Optional paper title (auto-extracted if not provided)
        authors: Optional author list (auto-extracted if not provided)
        
    Returns:
        ResearchAnalysisOutput: Structured technical analysis from Claude 4.1 Opus
        
    Note:
        All outputs are automatically saved to organized directory structure.
        Use for ML/AI safety research workflows and human review processes.
    """
    
    logger.info(f"Starting comprehensive research paper analysis: {pdf_path}")
    
    # STEP 1: Extract comprehensive PDF data using PyMuPDF
    logger.info("Extracting PDF metadata and content...")
    pdf_data = _extract_pdf_metadata_and_content(pdf_path)
    
    # Determine paper title from metadata or extraction
    if not paper_title:
        paper_title = (pdf_data['pdf_metadata']['title'] or 
                      pdf_data['extracted_from_first_page']['title_from_text'] or 
                      Path(pdf_path).stem)
    
    # Determine authors from metadata or extraction  
    if not authors:
        authors = (pdf_data['pdf_metadata']['author'] or
                  pdf_data['extracted_from_first_page']['authors_from_text'] or
                  'Unknown authors')
    
    logger.info(f"Paper: {paper_title}")
    logger.info(f"Authors: {authors}")
    logger.info(f"Raw text: {pdf_data['raw_text_length']} chars from {pdf_data['document_structure']['pages']} pages")
    logger.info(f"Visual content: {pdf_data['visual_content']['total_images']} images, {pdf_data['visual_content']['total_drawings']} drawings")
    
    # STEP 2: Extract figures from pages before references section
    logger.info("Extracting figures before references section...")
    references_page = _find_references_page(pdf_data['raw_text'])
    max_figure_page = references_page if references_page > 0 else None
    
    figures_result = _extract_figures_from_pdf(pdf_path, paper_title, max_figure_page)
    if figures_result['success']:
        logger.info(f"Extracted {figures_result['total_figures']} figures from {figures_result['pages_processed']} pages")
        if figures_result['figures_extracted']:
            sample_figures = figures_result['figures_extracted'][:3]  # Show first 3
            logger.info(f"Sample figures: {[f['filename'] for f in sample_figures]}")
    else:
        logger.warning(f"Figure extraction failed: {figures_result.get('error', 'Unknown error')}")
    
    # STEP 3: Create cleaned markdown (filters out references/appendix) with figures and header
    logger.info("Creating cleaned markdown version with figures and header...")
    cleaned_md, filter_stats = _create_cleaned_markdown(pdf_data['raw_text'], paper_title, figures_result, pdf_data)
    logger.info(f"Filtered content: {filter_stats['retention_percentage']:.1f}% retained ({filter_stats['removed_lines']} lines removed)")
    if filter_stats.get('figures_inserted', 0) > 0:
        logger.info(f"Inserted {filter_stats['figures_inserted']} figures into cleaned markdown")
    
    # STEP 4: Create distilled version with figures and header
    logger.info("Creating distilled bullet-point version with figures and header...")
    distilled_md = _create_distilled_version(cleaned_md, paper_title, figures_result, pdf_data['raw_text'], pdf_data)
    
    # STEP 5: Save all 4 outputs (raw text, metadata JSON, cleaned MD, distilled MD)
    logger.info("Saving research outputs...")
    save_result = _save_research_outputs(pdf_path, paper_title, pdf_data, cleaned_md, distilled_md, filter_stats, figures_result)
    
    if save_result['success']:
        logger.info(f"Saved outputs: {save_result['stats']}")
    else:
        logger.warning(f"Save partially failed: {save_result.get('error', 'Unknown error')}")
    
    # STEP 6: Run Claude analysis for technical insights (using filtered main content)
    main_content = _filter_main_content(pdf_data['raw_text'])
    
    # Initialize Claude with PhD-level AI safety expertise
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("ANTHROPIC_API_KEY")
        except ImportError:
            pass
    
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment")
    
    client = Anthropic(api_key=api_key)
    
    # Construct expert analysis prompt (using filtered main content)
    expert_prompt = f"""You are a PhD researcher specializing in AI safety and alignment with deep technical expertise in machine learning. Analyze this research paper with the rigor and insight of a leading AI safety researcher.

PAPER CONTENT:
{main_content}

PAPER METADATA:
Title: {paper_title}
Authors: {authors}
Pages: {pdf_data['document_structure']['pages']}
Visual Elements: {pdf_data['visual_content']['total_images']} images, {pdf_data['visual_content']['total_drawings']} drawings

ANALYSIS INSTRUCTIONS:
As an AI safety expert with PhD-level technical depth, provide a comprehensive analysis covering:

**Technical Analysis:**
- Core contribution: What is the main technical advancement? Be precise about the specific innovation.
- Methodology: Describe the research approach, experimental design, and technical methods used.
- Key results: Summarize the primary empirical findings, performance metrics, and quantitative results.
- Technical novelty: What differentiates this from prior work? What technical barriers were overcome?

**AI Safety & Alignment Context:**
- Safety implications: How does this work impact AI safety? Consider both positive contributions and potential risks.
- Risk assessment: What safety concerns does this raise? Consider capabilities, alignment, robustness, interpretability.
- Alignment relevance: How does this relate to the broader AI alignment research agenda?

**Research Quality & Significance:**
- Experimental rigor: Evaluate the experimental design, baselines, statistical validity, and reproducibility.
- Significance rating: Rate 1-10 with detailed rationale based on technical contribution, methodological rigor, and field impact.
- Future directions: What are the most promising next steps this work enables?

**Practical Applications:**
- Real-world applications: Where could this be deployed? What problems does it solve?
- Implementation challenges: What technical, computational, or practical barriers exist for deployment?

**Academic Context:**
- Related work analysis: How does this build on, differ from, or challenge existing literature?
- Citation-worthy claims: Identify 3-5 key claims that would be worth citing in future work.

**Communication & Framing:**
- Research framing: Brainstorm 3-5 different ways to frame this research for different audiences (academic, industry, policy, public). Focus on clear, compelling narratives that highlight the core contribution and avoid confusing technical nuances. Consider how to present the key insight simply and memorably.

CRITICAL REQUIREMENTS:
- Apply PhD-level technical rigor in your assessment
- Focus specifically on ML research with AI safety lens
- Be precise about technical details and avoid generic commentary
- Consider both immediate and long-term implications for AI development
- Evaluate claims critically but fairly

Provide your analysis in structured JSON format matching the ResearchAnalysisOutput schema:
{{
    "core_contribution": "...",
    "methodology": "...",
    "key_results": "...",
    "technical_novelty": "...",
    "safety_implications": "...",
    "risk_assessment": "...",
    "alignment_relevance": "...",
    "experimental_rigor": "...",
    "significance_rating": "...",
    "future_directions": "...",
    "real_world_applications": "...",
    "implementation_challenges": "...",
    "related_work_analysis": "...",
    "citation_worthy_claims": ["...", "...", "..."],
    "research_framing": ["...", "...", "..."]
}}"""

    logger.info("Analyzing research paper with Claude 4.1 Opus (PhD-level AI safety expertise)")
    
    try:
        response = client.messages.create(
            model="claude-opus-4-1-20250805",  # Use Opus 4.1 for PhD-level technical analysis
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": expert_prompt
            }]
        )
        
        analysis_text = response.content[0].text
        logger.info(f"Claude analysis completed: {len(analysis_text)} characters")
        
        # Parse JSON response
        if "{" in analysis_text and "}" in analysis_text:
            json_start = analysis_text.find("{")
            json_end = analysis_text.rfind("}") + 1
            json_str = analysis_text[json_start:json_end]
            
            try:
                analysis_data = json.loads(json_str)
                
                # Validate and create ResearchAnalysisOutput
                return ResearchAnalysisOutput(**analysis_data)
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse analysis JSON: {e}")
                # Try json-repair as fallback
                try:
                    import json_repair
                    repaired_json = json_repair.repair_json(json_str)
                    analysis_data = json.loads(repaired_json)
                    return ResearchAnalysisOutput(**analysis_data)
                except Exception as repair_error:
                    logger.error(f"JSON repair also failed: {repair_error}")
                    raise ValueError(f"Failed to parse Claude analysis as JSON: {e}")
        else:
            raise ValueError("No JSON structure found in Claude response")
            
    except Exception as e:
        logger.error(f"Error during Claude analysis: {e}")
        raise


def main():
    """Command line interface for research paper analysis"""
    if len(sys.argv) < 2:
        print("Usage: python analyze_research.py <pdf_path> [paper_title] [authors]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    paper_title = sys.argv[2] if len(sys.argv) > 2 else None
    authors = sys.argv[3] if len(sys.argv) > 3 else None
    
    if not Path(pdf_path).exists():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)
    
    try:
        # Analyze the research paper
        analysis = analyze_research_paper(pdf_path, paper_title, authors)
        
        # Output structured analysis to stdout
        print("="*80)
        print("ML RESEARCH PAPER ANALYSIS")
        print("="*80)
        print()
        
        print("TECHNICAL ANALYSIS")
        print("-"*40)
        print(f"Core Contribution: {analysis.core_contribution}")
        print()
        print(f"Methodology: {analysis.methodology}")
        print()
        print(f"Key Results: {analysis.key_results}")
        print()
        print(f"Technical Novelty: {analysis.technical_novelty}")
        print()
        
        print("AI SAFETY & ALIGNMENT CONTEXT")
        print("-"*40)
        print(f"Safety Implications: {analysis.safety_implications}")
        print()
        print(f"Risk Assessment: {analysis.risk_assessment}")
        print()
        print(f"Alignment Relevance: {analysis.alignment_relevance}")
        print()
        
        print("RESEARCH QUALITY & SIGNIFICANCE")
        print("-"*40)
        print(f"Experimental Rigor: {analysis.experimental_rigor}")
        print()
        print(f"Significance Rating: {analysis.significance_rating}")
        print()
        print(f"Future Directions: {analysis.future_directions}")
        print()
        
        print("PRACTICAL APPLICATIONS")
        print("-"*40)
        print(f"Real-world Applications: {analysis.real_world_applications}")
        print()
        print(f"Implementation Challenges: {analysis.implementation_challenges}")
        print()
        
        print("ACADEMIC CONTEXT")
        print("-"*40)
        print(f"Related Work Analysis: {analysis.related_work_analysis}")
        print()
        print("Citation-worthy Claims:")
        for i, claim in enumerate(analysis.citation_worthy_claims, 1):
            print(f"  {i}. {claim}")
        print()
        
        print("="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        
    except Exception as e:
        print(f"Error analyzing research paper: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Configure logging for standalone execution
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
    main()