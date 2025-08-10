#!/usr/bin/env python

import re
import logging
import os
from typing import Dict, List, Any
from urllib.parse import urlparse
from crewai import LLM

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

logger = logging.getLogger(__name__)


def analyze_pdf_with_multimodal_llm(images_data: List[Dict]) -> str:
    """
    Use Claude Sonnet multimodal to analyze entire PDF and extract key insights
    
    Args:
        images_data: List of slide images with base64 data
    
    Returns:
        Cleaned, structured content extracted by multimodal LLM
    """
    if not ANTHROPIC_AVAILABLE or not images_data:
        logger.warning("Multimodal analysis unavailable, falling back to OCR")
        return ""
    
    try:
        client = anthropic.Anthropic()
        
        # Prepare images for multimodal analysis
        image_contents = []
        for i, img_data in enumerate(images_data):
            base64_data = img_data.get('image_base64', '')
            if base64_data:
                image_contents.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64_data
                    }
                })
        
        if not image_contents:
            return ""
        
        # Create comprehensive analysis prompt
        analysis_prompt = """Extract slide content as markdown. Follow exact slide order and text.

**RULES**:
- Use EXACT text, headers, bullets as they appear
- Keep all URLs, QR codes, formulas, numbers, names exactly
- Remove duplicate slides only
- No preamble text - start directly with first slide

**CRITICAL: EXTRACT ALL RESOURCES**:
At the end, add a "RESOURCES FOUND:" section listing:
- All URLs (http/https links)
- Paper citations (titles with arXiv IDs like "arXiv:2502.12202")
- DOI references (like "10.1000/xyz123")
- Academic conferences (NeurIPS, ICML, ICLR, AAAI, IJCAI, CVPR, ACL, etc.)
- Author references and collaborators
- Organization/institution names with potential links
- GitHub repos, datasets, tools mentioned
- Academic journal references

**FORMAT**:
```
# [Exact slide title]
[Exact content/bullets]

# [Next slide title]
[Exact content/bullets]

RESOURCES FOUND:
- Paper Title - arXiv:2502.12202
- Conference Paper Title - NeurIPS 2024
- Website Name - https://example.com
- Dataset Name - https://github.com/user/repo
- Institution Name - https://institution.edu
```

**PRESERVE**:
- All slide titles/headers exactly
- Bullet points in original order  
- All URLs, arXiv IDs, DOIs, paper titles
- Technical terms and formulas
- Author names, institutions, citations
- Numbers and statistics
- Conference names and years

**ACADEMIC PATTERNS TO LOOK FOR**:
- arXiv preprint references (format: arXiv:YYMM.NNNNN)
- DOI patterns (format: 10.XXXX/...)
- Conference papers: "NeurIPS", "ICML", "ICLR", "AAAI", "CVPR", "ACL", etc.
- Journal abbreviations and full names
- Author citations with years

**SKIP ONLY**:
- Duplicate slides
- Watermarks  
- Headers/footers

Start directly with the first slide content, end with RESOURCES FOUND section."""

        # Make API call with all images
        message_content = [{"type": "text", "text": analysis_prompt}] + image_contents
        
        logger.info(f"Analyzing {len(image_contents)} slides with Claude multimodal")
        
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": message_content
            }]
        )
        
        cleaned_content = response.content[0].text.strip()
        
        # Clean up the content
        cleaned_content = cleanup_multimodal_output(cleaned_content)
        
        logger.info(f"Multimodal analysis complete: {len(cleaned_content)} characters")
        return cleaned_content
        
    except Exception as e:
        logger.error(f"Multimodal PDF analysis failed: {e}")
        return ""


def cleanup_multimodal_output(content: str) -> str:
    """
    Clean up multimodal LLM output by removing preambles and excessive whitespace
    
    Args:
        content: Raw multimodal analysis output
    
    Returns:
        Cleaned content ready for Coda
    """
    if not content:
        return content
    
    # Remove common preamble phrases
    preambles = [
        "Here's the exact content extraction from the presentation slides",
        "Here is the exact content extraction from the presentation slides", 
        "Following the specified format:",
        "in markdown format:",
        "Here's the structured extraction",
        "Here is the structured extraction"
    ]
    
    lines = content.split('\n')
    cleaned_lines = []
    skip_until_content = True
    
    for line in lines:
        line = line.strip()
        
        # Skip preamble lines
        if skip_until_content:
            # Look for first actual slide header
            if line.startswith('#') and not any(preamble.lower() in line.lower() for preamble in preambles):
                skip_until_content = False
                cleaned_lines.append(line)
            elif not any(preamble.lower() in line.lower() for preamble in preambles) and line and not line.startswith('**'):
                # If we hit actual content (not preamble), start including
                skip_until_content = False
                cleaned_lines.append(line)
        else:
            # Include all content after preamble
            cleaned_lines.append(line)
    
    # Join and reduce multiple blank lines to single blank lines
    result = '\n'.join(cleaned_lines)
    
    # Replace multiple consecutive newlines with max 2 newlines
    import re
    result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)
    
    return result.strip()


def clean_slide_text(raw_content: str) -> str:
    """
    Use LLM to clean up messy slide text extraction artifacts
    
    Args:
        raw_content: Raw text extracted from PDF/PPTX slides
    
    Returns:
        Cleaned, readable text suitable for content generation
    """
    if not raw_content or not raw_content.strip():
        return raw_content
    
    # If content is too short, probably clean enough already
    if len(raw_content.strip()) < 100:
        return raw_content.strip()
    
    try:
        llm = LLM(
            model="anthropic/claude-haiku-3-20240307",  # Fast, cheap model for cleaning
            max_retries=2
        )
        
        # Create cleaning prompt
        cleaning_prompt = f"""Clean up this slide text that was extracted from a PDF. Remove:
- Math equation artifacts and garbled symbols
- Repeated headers/footers 
- Random formatting characters
- Broken table layouts
- Page numbers and slide metadata

Keep the meaningful content and structure. Make it readable and coherent:

---SLIDE TEXT---
{raw_content}
---END SLIDE TEXT---

Return only the cleaned text, no explanations."""

        logger.info(f"Cleaning {len(raw_content)} characters of slide content")
        
        # Get cleaned content from LLM
        cleaned_result = llm.call(cleaning_prompt)
        
        # Extract the actual text response
        if hasattr(cleaned_result, 'content'):
            cleaned_content = cleaned_result.content
        elif isinstance(cleaned_result, str):
            cleaned_content = cleaned_result
        else:
            cleaned_content = str(cleaned_result)
        
        cleaned_content = cleaned_content.strip()
        
        # Basic validation - make sure we didn't lose too much content
        if len(cleaned_content) < len(raw_content) * 0.3:  # Lost more than 70%
            logger.warning("LLM cleaning removed too much content, using original")
            return raw_content
        
        logger.info(f"Cleaned content: {len(raw_content)} → {len(cleaned_content)} characters")
        return cleaned_content
        
    except Exception as e:
        logger.error(f"Error cleaning slide content: {e}")
        logger.info("Falling back to original content")
        return raw_content


def clean_slides_text(slides: list) -> list:
    """
    Clean content for multiple slides while preserving structure
    
    Args:
        slides: List of slide dicts with 'content' field
    
    Returns:
        List of slides with cleaned content
    """
    cleaned_slides = []
    
    for slide in slides:
        if isinstance(slide, dict) and 'content' in slide:
            cleaned_slide = slide.copy()
            cleaned_slide['content'] = clean_slide_text(slide['content'])
            cleaned_slides.append(cleaned_slide)
        else:
            cleaned_slides.append(slide)  # Pass through unchanged
    
    return cleaned_slides


def extract_resources_from_content(content: str) -> list:
    """
    Extract references to papers, websites, and resources from slide content
    
    Args:
        content: Full slide content text
    
    Returns:
        List of resource dicts with 'name' and 'url' keys
    """
    if not content:
        return []
    
    resources = []
    
    # First, check if multimodal LLM added a "RESOURCES FOUND:" section
    if "RESOURCES FOUND:" in content:
        resources.extend(parse_resources_section(content))
    
    # Also do pattern-based extraction for fallback/additional resources
    resources.extend(extract_resources_by_patterns(content))
    
    # Remove duplicates based on URL and normalize similar entries
    seen_urls = set()
    seen_names = set()
    unique_resources = []
    
    for resource in resources:
        url = resource['url']
        name = resource['name'].lower().strip()
        
        # Skip if we've seen this URL already
        if url in seen_urls:
            continue
            
        # Skip if we've seen a very similar name (for non-URL resources)
        name_key = ''.join(c for c in name if c.isalnum())
        if name_key and len(name_key) > 10 and name_key in seen_names:
            continue
            
        seen_urls.add(url)
        if name_key and len(name_key) > 10:
            seen_names.add(name_key)
        unique_resources.append(resource)
    
    return unique_resources


def parse_resources_section(content: str) -> list:
    """
    Parse the "RESOURCES FOUND:" section added by multimodal LLM
    
    Args:
        content: Content with RESOURCES FOUND section
    
    Returns:
        List of parsed resource dicts
    """
    resources = []
    lines = content.split('\n')
    in_resources_section = False
    
    for line in lines:
        line = line.strip()
        
        if line.startswith("RESOURCES FOUND:"):
            in_resources_section = True
            continue
            
        if in_resources_section:
            if not line or line.startswith("#"):  # End of resources section
                break
                
            if line.startswith("- ") and " - " in line:
                # Parse format: "- Paper Title - URL or arXiv:ID or DOI"
                resource_text = line[2:].strip()  # Remove "- "
                
                if " - " in resource_text:
                    parts = resource_text.split(" - ", 1)
                    name = parts[0].strip()
                    identifier = parts[1].strip()
                    
                    # Convert identifier to full URL
                    url = convert_identifier_to_url(identifier)
                    
                    if url:
                        resources.append({
                            'name': name,
                            'url': url,
                            'context': f"Found in resources section: {resource_text}"
                        })
                        logger.debug(f"Parsed resource: {name} -> {url}")
    
    return resources


def convert_identifier_to_url(identifier: str) -> str:
    """
    Convert various identifiers (arXiv:ID, DOI, URLs, academic references) to full URLs
    
    Args:
        identifier: arXiv ID, DOI, URL string, or academic reference
    
    Returns:
        Full URL or empty string if conversion fails
    """
    identifier = identifier.strip()
    
    # Already a URL
    if identifier.startswith(('http://', 'https://')):
        return identifier
    
    # Add https to www. domains
    if identifier.startswith('www.'):
        return 'https://' + identifier
    
    # arXiv patterns - multiple formats
    if identifier.lower().startswith('arxiv:') or identifier.lower().startswith('arxiv '):
        arxiv_id = identifier[6:].strip()  # Remove "arXiv:" or "arXiv " prefix
        return f'https://arxiv.org/abs/{arxiv_id}'
    
    # Direct arXiv ID patterns
    # New format: YYMM.NNNNN (2007+)
    arxiv_new_pattern = r'^(\d{4}\.\d{4,5}(v\d+)?)$'
    if re.match(arxiv_new_pattern, identifier):
        return f'https://arxiv.org/abs/{identifier}'
    
    # Old format: subject-class/YYMMnnn (pre-2007)
    arxiv_old_pattern = r'^([a-z-]+/\d{7}(v\d+)?)$'
    if re.match(arxiv_old_pattern, identifier):
        return f'https://arxiv.org/abs/{identifier}'
    
    # DOI patterns
    if identifier.lower().startswith('doi:'):
        doi = identifier[4:].strip()  # Remove "doi:" prefix
        return f'https://doi.org/{doi}'
    
    # Direct DOI pattern (10.XXXX/...)
    doi_pattern = r'^10\.\d+/.+'
    if re.match(doi_pattern, identifier):
        return f'https://doi.org/{identifier}'
    
    # Academic conference/journal patterns
    # Look for patterns like "NeurIPS 2024", "ICML 2023", etc.
    conference_pattern = r'^(NeurIPS|ICML|ICLR|AAAI|IJCAI|UAI|AISTATS|COLT|KDD|WWW|SIGIR|RecSys|WSDM|CHI|UIST|CVPR|ICCV|ECCV|ACL|EMNLP|NAACL|COLING)\s+\d{4}$'
    if re.match(conference_pattern, identifier, re.IGNORECASE):
        # For conference proceedings, we can't generate direct URLs without paper titles
        # Return empty string - these should be detected in context
        return ""
    
    # PubMed ID pattern
    if identifier.lower().startswith('pmid:'):
        pmid = identifier[5:].strip()
        if pmid.isdigit():
            return f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'
    
    # Simple domain patterns (github.com/user/repo, etc.)
    domain_pattern = r'^[a-zA-Z0-9.-]+\.(com|org|edu|net|gov|io|ai)(/.*)?$'
    if re.match(domain_pattern, identifier):
        return 'https://' + identifier
    
    return ""  # Could not convert


def extract_resources_by_patterns(content: str) -> list:
    """
    Extract resources using regex patterns (fallback method)
    
    Args:
        content: Full slide content text
    
    Returns:
        List of resource dicts
    """
    resources = []
    lines = content.split('\n')
    
    # URL patterns - simple and robust
    url_pattern = r'https?://[^\s\)\]]+|www\.[^\s\)\]]+|[a-zA-Z0-9.-]+\.(com|org|edu|net|gov|io|ai)\b[^\s\)\]]*'
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith("RESOURCES FOUND:"):
            continue
        
        # Find URLs in the line
        urls = re.findall(url_pattern, line, re.IGNORECASE)
        
        for url in urls:
            # Clean up URL (remove trailing punctuation)
            clean_url = url.rstrip('.,;:!?)')
            
            # Skip if URL is too short or looks malformed
            if len(clean_url) < 8:
                continue
            
            # Add protocol if missing
            if not clean_url.startswith(('http://', 'https://')):
                if clean_url.startswith('www.'):
                    clean_url = 'https://' + clean_url
                else:
                    clean_url = 'https://' + clean_url
            
            # Extract resource name from context
            resource_name = extract_resource_name(line, url)
            
            logger.debug(f"Found URL: {clean_url} in line: {line[:50]}")
            
            resources.append({
                'name': resource_name,
                'url': clean_url,
                'context': line[:100]  # Keep some context
            })
    
    return resources


def extract_resource_name(line: str, url: str) -> str:
    """
    Extract a meaningful name for a resource from the line context
    
    Args:
        line: The line containing the URL
        url: The URL found in the line
    
    Returns:
        Descriptive name for the resource
    """
    # Remove the URL from the line to get potential name
    line_without_url = line.replace(url, '').strip()
    
    # Clean up common prefixes/suffixes
    line_clean = re.sub(r'^[-•*\s]+|[-•*\s]+$', '', line_without_url)
    line_clean = re.sub(r'^(source:|reference:|see:|from:|paper:|study:|website:|link:)\s*', '', line_clean, flags=re.IGNORECASE)
    
    # If we have meaningful text, use it
    if line_clean and len(line_clean.strip()) > 3:
        # Limit length and clean up
        name = line_clean.strip()[:60]
        if len(line_clean) > 60:
            name = name.rsplit(' ', 1)[0] + '...'  # Break at word boundary
        return name
    
    # Extract domain name as fallback
    try:
        parsed = urlparse(url if url.startswith(('http://', 'https://')) else 'https://' + url)
        domain = parsed.netloc.lower()
        
        # Clean up common prefixes
        domain = re.sub(r'^www\.', '', domain)
        
        # Capitalize for readability
        return domain.replace('.', ' ').title().replace(' Com', '.com').replace(' Org', '.org')
        
    except:
        return "Resource"


def format_resources_for_coda(resources: list) -> str:
    """
    Format resources for Coda "Resources" column in specified format
    
    Args:
        resources: List of resource dicts with 'name' and 'url'
    
    Returns:
        Formatted string: "{resource_name} - {resource_url}"
    """
    if not resources:
        return ""
    
    formatted_items = []
    for resource in resources:
        name = resource.get('name', 'Resource')
        url = resource.get('url', '')
        
        if url:  # Only include if we have a valid URL
            formatted_items.append(f"{name} - {url}")
    
    return '\n'.join(formatted_items)


def format_slides_as_markdown(slides: list, images_data: list = None) -> str:
    """
    Convert cleaned slides into structured markdown with hierarchy
    
    Args:
        slides: List of cleaned slide dicts with 'content' field
        images_data: Optional list of image dicts for adding image placeholders
    
    Returns:
        Markdown formatted string with slide hierarchy and image indicators
    """
    if not slides:
        return ""
    
    markdown_parts = []
    
    for slide in slides:
        if isinstance(slide, dict):
            page_num = slide.get('page', slide.get('slide', '?'))
            content = slide.get('content', '').strip()
            
            if content and content != f"[PAGE {page_num} - NO TEXT EXTRACTED]":
                # Add horizontal rule as page break (except for first slide)
                if markdown_parts:  # Not the first slide
                    markdown_parts.append("---")
                    markdown_parts.append("")  # Empty line after HR
                
                # Add image placeholder if images are available for this slide
                if images_data:
                    image_placeholder = get_image_placeholder(page_num, content, images_data)
                    if image_placeholder:
                        markdown_parts.append(image_placeholder)
                        markdown_parts.append("")  # Empty line after image
                
                # Process content to preserve structure
                formatted_content = format_slide_content(content)
                markdown_parts.append(formatted_content)
                markdown_parts.append("")  # Empty line after content
    
    return "\n".join(markdown_parts).strip()


def format_slide_content(content: str) -> str:
    """
    Format individual slide content with basic markdown structure
    
    Args:
        content: Cleaned slide content string
    
    Returns:
        Content formatted with basic markdown structure
    """
    if not content:
        return ""
    
    lines = content.split('\n')
    formatted_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            formatted_lines.append("")
            continue
        
        # Convert bullet points and dashes to markdown bullets
        if line.startswith(('•', '▪', '▫', '‣', '⁃')) or line.startswith('- '):
            formatted_lines.append(f"- {line[1:].strip()}")
        elif line.startswith(('*', '·')) and len(line) > 2:
            formatted_lines.append(f"- {line[1:].strip()}")
        # Convert numbered lists
        elif line and line[0].isdigit() and len(line) > 2 and line[1:3] in ['. ', ') ']:
            formatted_lines.append(line)  # Keep numbered lists as-is
        # Potential headers (short lines, often all caps or title case)
        elif len(line) < 80 and (line.isupper() or line.istitle()) and not line.endswith('.'):
            formatted_lines.append(f"### {line}")
        else:
            formatted_lines.append(line)
    
    return "\n".join(formatted_lines)


def get_image_placeholder(page_num: int, content: str, images_data: list) -> str:
    """
    Generate image placeholder text based on slide content and available images
    
    Args:
        page_num: Slide/page number (1-indexed)
        content: Cleaned text content from slide
        images_data: List of image dicts with metadata
    
    Returns:
        Image placeholder string or empty string if no image
    """
    # Find corresponding image data
    image_info = None
    for img in images_data:
        if img.get('page') == page_num:
            image_info = img
            break
    
    if not image_info:
        return ""
    
    # Generate brief description based on content analysis
    description = infer_image_content(content)
    
    return f"*[Image: {description}]*"


def infer_image_content(content: str) -> str:
    """
    Infer what type of visual content might be present based on text content
    
    Args:
        content: Cleaned slide text content
    
    Returns:
        Brief description of likely image content
    """
    if not content:
        return "visual content"
    
    content_lower = content.lower()
    
    # Chart/graph indicators
    chart_keywords = ['chart', 'graph', 'plot', 'figure', 'data', 'results', 'analysis', 'percentage', '%', 'trend']
    if any(keyword in content_lower for keyword in chart_keywords):
        if 'result' in content_lower or 'analysis' in content_lower:
            return "chart showing results/analysis"
        elif any(word in content_lower for word in ['trend', 'over time', 'growth']):
            return "trend chart/graph"
        else:
            return "chart/graph with data"
    
    # Diagram/architecture indicators
    diagram_keywords = ['architecture', 'system', 'model', 'framework', 'process', 'workflow', 'pipeline']
    if any(keyword in content_lower for keyword in diagram_keywords):
        return "system/process diagram"
    
    # Screenshot/interface indicators  
    ui_keywords = ['interface', 'screen', 'demo', 'example', 'tool', 'platform']
    if any(keyword in content_lower for keyword in ui_keywords):
        return "interface/demo screenshot"
    
    # Mathematical/technical indicators
    math_keywords = ['equation', 'formula', 'algorithm', 'method', 'approach', 'technique']
    if any(keyword in content_lower for keyword in math_keywords):
        return "technical diagram/equations"
    
    # Default fallback
    return "slide visual content"


def get_cleaned_text(content_dict: dict) -> dict:
    """
    Clean and process slide content using multimodal LLM when images available
    
    Args:
        content_dict: Result from get_slide_text() or get_slide_content()
    
    Returns:
        Same dict with cleaned content and markdown format
    """
    if not content_dict.get('success'):
        return content_dict
    
    result = content_dict.copy()
    
    # Try multimodal analysis first if images are available
    images_data = result.get('images', [])
    if images_data and ANTHROPIC_AVAILABLE:
        logger.info("Using multimodal LLM for comprehensive PDF analysis")
        
        # Get high-quality analysis from Claude multimodal
        multimodal_content = analyze_pdf_with_multimodal_llm(images_data)
        
        if multimodal_content:
            # Use multimodal analysis as the primary content
            result['content'] = multimodal_content
            result['content_markdown'] = multimodal_content  # Already in markdown format
            result['processing_method'] = 'multimodal_llm'
            
            # Extract resources from the cleaned multimodal content
            resources = extract_resources_from_content(multimodal_content)
        else:
            # Fallback to OCR-based processing
            logger.warning("Multimodal analysis failed, falling back to OCR processing")
            result = process_with_ocr_fallback(result)
            resources = extract_resources_from_content(result.get('content', ''))
    else:
        # No images available or no multimodal support - use OCR approach
        logger.info("Using OCR-based processing (no images or multimodal unavailable)")
        result = process_with_ocr_fallback(result) 
        resources = extract_resources_from_content(result.get('content', ''))
    
    # Add QR code URLs if visual analysis was performed and QR codes found
    if images_data:
        try:
            from far_comms.utils.visual_analyzer import detect_qr_codes_in_images
            qr_codes = detect_qr_codes_in_images(images_data)
            
            # Add QR URLs to resources
            for qr in qr_codes:
                if qr.get('type') == 'url':
                    url = qr.get('url')
                    page_num = qr.get('page', '?')
                    resources.append({
                        'name': f"QR Code (Slide {page_num})",
                        'url': url,
                        'context': f"QR code found on slide {page_num}"
                    })
                    
        except ImportError:
            pass  # QR detection not available
        except Exception as e:
            logger.warning(f"Error detecting QR codes for resources: {e}")
    
    if resources:
        result['resources'] = resources
        result['resources_formatted'] = format_resources_for_coda(resources)
    
    logger.info(f"Processed slide content for {result.get('file_name', 'unknown file')} using {result.get('processing_method', 'ocr')}")
    
    return result


def process_with_ocr_fallback(result: dict) -> dict:
    """
    Process content using OCR-based approach (fallback)
    
    Args:
        result: Content dictionary from slide extraction
    
    Returns:
        Processed content dictionary
    """
    # Clean full content
    if 'content' in result:
        result['content'] = clean_slide_text(result['content'])
    
    # Clean individual slides
    if 'slides' in result:
        result['slides'] = clean_slides_text(result['slides'])
    
    # Create markdown version with hierarchy
    if 'slides' in result:
        images_data = result.get('images', [])
        result['content_markdown'] = format_slides_as_markdown(result['slides'], images_data)
    
    result['processing_method'] = 'ocr_fallback'
    return result