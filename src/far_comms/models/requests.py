#!/usr/bin/env python

from pydantic import BaseModel, HttpUrl
from enum import Enum

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
    speaker: str | None = None

# ============================================================================
# PROMOTE_TALK FUNCTION MODELS
# ============================================================================

class TalkRequest(BaseModel):
    """Input model for promote_talk function - works for both API and Coda"""
    speaker: str
    title: str
    event: str
    affiliation: str
    yt_full_link: str | HttpUrl
    resource_url: str | HttpUrl | None = None
    transcript: str

class TalkPromotionOutput(BaseModel):
    """Output from the talk promotion crew - keys match Coda column names"""
    paragraph_ai: str  # "Paragraph (AI)" column
    hooks_ai: list[str]  # "Hooks (AI)" column - 5 hooks 
    li_content: str  # "LI content" column
    x_content: str  # "X content" column
    eval_notes: str  # Rubric breakdown and checklist with compliance notes

# ============================================================================
# PROMOTE_RESEARCH FUNCTION MODELS (TODO)
# ============================================================================

# class ResearchRequest(BaseModel):
#     """Input model for promote_research function"""
#     pass

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