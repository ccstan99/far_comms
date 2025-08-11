#!/usr/bin/env python

"""
Simple test script for ML research paper analyzer - text-only for speed.
"""

import logging
import json
import os
import sys
from pathlib import Path
from far_comms.models.requests import ResearchRequest, ResearchAnalysisOutput
from langchain_community.document_loaders import PyPDFLoader
from anthropic import Anthropic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _filter_main_content(text_content: str) -> str:
    """Filter PDF content to focus on main paper, excluding bibliography, references, appendix."""
    import re
    
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
    
    # Also look for numbered reference lists
    for i in range(end_idx):
        line = lines[i].strip()
        if re.match(r'^\[\d+\]\s+\w+', line) or re.match(r'^\d+\.\s+\w+.*\d{4}', line):
            ref_count = 0
            for j in range(i, min(i+5, end_idx)):
                if re.match(r'^\[\d+\]|\^\d+\.', lines[j].strip()):
                    ref_count += 1
            if ref_count >= 2:
                end_idx = i
                logger.info(f"Found numbered references starting at line {i}")
                break
    
    main_content = '\n'.join(lines[:end_idx])
    
    original_words = len(text_content.split())
    filtered_words = len(main_content.split())
    logger.info(f"Filtered content: {original_words} → {filtered_words} words ({filtered_words/original_words*100:.1f}% retained)")
    
    return main_content

def analyze_research_paper_simple(pdf_path: str) -> ResearchAnalysisOutput:
    """Analyze ML research paper with Claude 4.1 Opus - text only for speed."""
    
    # Extract PDF text content only
    logger.info(f"Extracting text from research paper: {pdf_path}")
    text_loader = PyPDFLoader(pdf_path)
    text_docs = text_loader.load()
    text_content = "\n\n".join([doc.page_content for doc in text_docs])
    
    # Filter to main content only
    main_content = _filter_main_content(text_content)
    
    if not main_content:
        raise ValueError(f"Failed to extract content from PDF: {pdf_path}")
    
    # Initialize Claude 4.1 Opus
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
{main_content}

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
            model="claude-opus-4-1-20250805",
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
                return ResearchAnalysisOutput(**analysis_data)
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse analysis JSON: {e}")
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
    """Simple command line test"""
    if len(sys.argv) < 2:
        print("Usage: python test_analyze_research_simple.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    if not Path(pdf_path).exists():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)
    
    try:
        analysis = analyze_research_paper_simple(pdf_path)
        
        print("="*80)
        print("ML RESEARCH PAPER ANALYSIS (TEXT-ONLY)")
        print("="*80)
        print(f"Core Contribution: {analysis.core_contribution}")
        print(f"Safety Implications: {analysis.safety_implications}")
        print(f"Significance Rating: {analysis.significance_rating}")
        print("="*80)
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()