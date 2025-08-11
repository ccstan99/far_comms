#!/usr/bin/env python

"""
Standalone ML research paper analyzer with AI safety PhD-level expertise.
Processes ML research papers and outputs structured technical analysis.
"""

import logging
import json
import os
import sys
from pathlib import Path
from far_comms.models.requests import ResearchRequest, ResearchAnalysisOutput
from far_comms.utils.content_preprocessor import extract_pdf_content
from anthropic import Anthropic

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

def analyze_research_paper(pdf_path: str, paper_title: str = None, authors: str = None) -> ResearchAnalysisOutput:
    """
    Analyze ML research paper with PhD-level AI safety technical expertise.
    
    Args:
        pdf_path: Path to the research paper PDF
        paper_title: Optional paper title (extracted from PDF if not provided)
        authors: Optional author list (extracted from PDF if not provided)
        
    Returns:
        ResearchAnalysisOutput with structured technical analysis
    """
    
    # Extract PDF content - text first, then selective visual analysis
    logger.info(f"Extracting content from research paper: {pdf_path}")
    from langchain_community.document_loaders import PyPDFLoader
    
    # Get text content first
    text_loader = PyPDFLoader(pdf_path)
    text_docs = text_loader.load()
    text_content = "\n\n".join([doc.page_content for doc in text_docs])
    
    # Only do visual analysis if we detect figure references in text
    visual_elements = []
    if _has_figures_or_tables(text_content):
        logger.info("Detected figure/table references - performing selective visual analysis")
        full_pdf_content = extract_pdf_content(pdf_path, "research_paper")
        visual_elements = full_pdf_content.get("visual_elements", [])
    else:
        logger.info("No figure/table references detected - skipping visual analysis")
    
    pdf_content = {
        "enhanced_content": text_content,
        "visual_elements": visual_elements
    }
    
    # Filter content to focus on main paper (exclude bibliography, references, appendix)
    main_content = _filter_main_content(pdf_content["enhanced_content"])
    pdf_content["enhanced_content"] = main_content
    
    if not pdf_content["enhanced_content"]:
        raise ValueError(f"Failed to extract content from PDF: {pdf_path}")
    
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
    
    # Construct expert analysis prompt
    expert_prompt = f"""You are a PhD researcher specializing in AI safety and alignment with deep technical expertise in machine learning. Analyze this research paper with the rigor and insight of a leading AI safety researcher.

PAPER CONTENT:
{pdf_content['enhanced_content']}

VISUAL ELEMENTS (if any):
{json.dumps(pdf_content['visual_elements'], indent=2) if pdf_content['visual_elements'] else "None"}

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
    "citation_worthy_claims": ["...", "...", "..."]
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
    logging.getLogger('PIL.PngImagePlugin').setLevel(logging.WARNING) 
    logging.getLogger('httpx').setLevel(logging.WARNING)
    main()