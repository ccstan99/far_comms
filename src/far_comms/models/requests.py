#!/usr/bin/env python

from pydantic import BaseModel, HttpUrl, Field
from enum import Enum
from typing import Union, Optional

# ============================================================================
# SHARED TYPES
# ============================================================================

class FunctionName(str, Enum):
    """Available crew function names for Coda webhook"""
    PROMOTE_TALK = "promote_talk"
    PREPARE_TALK = "prepare_talk"
    PROMOTE_RESEARCH = "promote_research" 
    PROMOTE_EVENT = "promote_event"

class CodaWebhookRequest(BaseModel):
    thisRow: str
    docId: str
    speaker: Optional[str] = None

# ============================================================================
# PROMOTE_TALK FUNCTION MODELS
# ============================================================================

class TalkRequest(BaseModel):
    """Input model for promote_talk function - works for both API and Coda"""
    speaker: str
    title: str
    event: str
    affiliation: str
    yt_full_link: Union[str, HttpUrl]
    resource_url: Optional[Union[str, HttpUrl]] = None
    transcript: str

class TalkPromotionOutput(BaseModel):
    """Output from the talk promotion crew - keys match Coda column names"""
    paragraph_ai: str  # "Paragraph (AI)" column
    hooks_ai: list[str]  # "Hooks (AI)" column - 5 hooks 
    li_content: str  # "LI content" column
    x_content: str  # "X content" column
    eval_notes: str  # Rubric breakdown and checklist with compliance notes

# ============================================================================
# PROMOTE_RESEARCH FUNCTION MODELS
# ============================================================================

class ResearchRequest(BaseModel):
    """Input model for analyze_research function - ML research paper analysis"""
    pdf_path: str = Field(
        ...,
        description="Path to PDF file (local path or URL). Examples: 'data/research/paper.pdf' or 'https://arxiv.org/pdf/2301.00001.pdf'",
        example="data/research/APE - paper.pdf"
    )
    project_name: str = Field(
        ...,
        description="Short project name for directory structure and file organization (e.g., 'APE_eval', 'constitutional_ai')",
        example="APE_eval"
    )
    
class ResearchAnalysisOutput(BaseModel):
    """Output from research analysis - structured insights for ML papers"""
    # Technical Analysis
    core_contribution: str = Field(
        description="Main technical contribution in 2-3 sentences",
        example="This paper introduces a novel architecture combining transformers with reinforcement learning for improved AI safety alignment."
    )
    methodology: str = Field(
        description="Research methodology and approach", 
        example="The authors employ a controlled experimental design with synthetic datasets and real-world benchmarks to validate their approach."
    )
    key_results: str = Field(
        description="Primary findings and results",
        example="The proposed method achieves 23% improvement in alignment metrics while maintaining 95% performance on standard benchmarks."
    )
    technical_novelty: str = Field(
        description="What makes this work technically novel",
        example="Novel integration of constitutional AI principles with reinforcement learning from human feedback, addressing previous limitations."
    )
    
    # AI Safety & Alignment Context
    safety_implications: str = Field(
        description="Implications for AI safety and alignment",
        example="This work directly addresses capability-control problems and provides actionable insights for safer AI deployment."
    )
    risk_assessment: str = Field(
        description="Potential risks or concerns raised",
        example="The approach may be vulnerable to reward hacking and could potentially be misused for deceptive alignment scenarios."
    )
    alignment_relevance: str = Field(
        description="Relevance to AI alignment research",
        example="Highly relevant to current alignment research agenda, particularly for scalable oversight and value learning."
    )
    
    # Research Quality & Significance  
    experimental_rigor: str = Field(
        description="Assessment of experimental design and validation",
        example="Strong experimental design with appropriate controls, statistical significance testing, and comprehensive ablation studies."
    )
    significance_rating: str = Field(
        description="Overall significance to the field (1-10 with rationale)",
        example="8/10 - Significant contribution to AI alignment with immediate practical applications, though limited by scope."
    )
    future_directions: str = Field(
        description="Promising future research directions",
        example="Extension to multimodal settings, integration with constitutional AI, and large-scale deployment studies."
    )
    
    # Practical Applications
    real_world_applications: str = Field(
        description="Potential real-world applications",
        example="Applicable to chatbot safety, autonomous vehicle decision-making, and content moderation systems."
    )
    implementation_challenges: str = Field(
        description="Key challenges for practical implementation",
        example="Computational overhead, requirement for extensive human feedback, and potential scalability issues."
    )
    
    # Academic Context
    related_work_analysis: str = Field(
        description="How it builds on or differs from prior work",
        example="Builds on Christiano et al. (2017) but differs by incorporating constitutional principles and addressing reward specification challenges."
    )
    citation_worthy_claims: list[str] = Field(
        description="Key claims worth citing (3-5 bullet points)",
        example=[
            "Constitutional AI can be effectively combined with RLHF to improve alignment",
            "The proposed method reduces alignment tax by 23% compared to baseline approaches", 
            "Human feedback quality significantly impacts final model performance"
        ]
    )
    
    # Communication & Framing
    research_framing: list[str] = Field(
        description="3-5 different ways to frame this research for different audiences (academic, industry, policy, public)",
        example=[
            "Academic framing: Novel evaluation methodology that shifts focus from persuasion outcomes to intent, addressing critical gap in current benchmarks",
            "Industry framing: Easy-to-deploy evaluation tool revealing that most frontier models readily attempt harmful persuasion when prompted",
            "Policy framing: Current AI safety guardrails insufficient - models will advocate for terrorism and violence, requiring stronger regulation",
            "Public framing: AI systems designed to be helpful can be easily misused for large-scale manipulation campaigns on harmful topics"
        ]
    )

class ResearchAnalysisResponse(BaseModel):
    """Response from analyze_research endpoint"""
    status: str = Field(description="Status of the analysis: 'success' or 'failed'")
    message: str = Field(description="Status message or error details")
    analysis: Optional[ResearchAnalysisOutput] = Field(
        None,
        description="Structured research analysis (null if analysis failed)"
    )
    files_saved: Optional[dict] = Field(
        None,
        description="Information about saved Markdown file (primary format for human review)",
        example={
            "markdown_path": "output/APE_Attempt_to_Persuade_Eval.md", 
            "filename": "APE_Attempt_to_Persuade_Eval"
        }
    )

# ============================================================================
# PROMOTE_EVENT FUNCTION MODELS (TODO) 
# ============================================================================

# class EventRequest(BaseModel):
#     """Input model for promote_event function"""
#     pass


class CodaIds:
    """Coda document, table, and row identifiers"""
    def __init__(self, doc_id: str, table_id: str, row_id: str):
        self.doc_id = doc_id
        self.table_id = table_id
        self.row_id = row_id
    
    @classmethod
    def from_this_row(cls, doc_id: str, this_row: str) -> 'CodaIds':
        """Create CodaIds by splitting this_row into table_id/row_id"""
        table_id, row_id = this_row.split('/')
        return cls(doc_id=doc_id, table_id=table_id, row_id=row_id)
    
    def model_dump(self):
        """For compatibility with existing code"""
        return {
            "doc_id": self.doc_id,
            "table_id": self.table_id,
            "row_id": self.row_id
        }