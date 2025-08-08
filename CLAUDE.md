# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the FastAPI Server
```bash
# Activate conda environment and run server with proper Python path
conda activate llm-agents
PYTHONPATH=src uvicorn far_comms.main:app --reload

# Expose server via cloudflared tunnel (for webhook testing)
cloudflared tunnel --url http://localhost:8000
```

### Alternative Crew Execution
```bash
# Direct crew execution (deprecated - use FastAPI endpoints instead)
uv run far_comms
```

### Installation
```bash
# This project uses uv for dependency management
uv sync
```

## Architecture Overview

### Core System: Multi-Agent Content Generation Pipeline

This is a **CrewAI-based multi-agent system** that processes academic talk transcripts and generates high-quality social media content for FAR.AI. The system uses specialized agents working sequentially to analyze, create, and quality-control content.

### Key Components

**1. FastAPI Application (`src/far_comms/main.py`)**
- HTTP endpoints for content generation requests
- Coda webhook integration for automated processing
- Background task execution with status tracking
- Content assembly and Coda database updates

**2. Multi-Agent Crews (`src/far_comms/crews/`)**
- `PromoteTalkCrew`: 7-agent pipeline for talk content generation
- Each crew uses YAML-based agent and task configurations
- Sequential processing with quality control checkpoints

**3. Coda Integration (`src/far_comms/tools/coda_tool.py`)**
- Bidirectional integration with Coda database
- Reads talk metadata, updates processing status
- Batch operations with 24-hour caching

**4. Style Guide System (`docs/`)**
- Platform-specific guidelines (LinkedIn, Twitter/X)
- High-performing content examples
- Brand voice and compliance requirements

### Agent Architecture (PromoteTalkCrew)

The system uses a **7-agent sequential pipeline**:

1. **transcript_analyzer_agent**: Preserves speaker's original content and structure
2. **hook_specialist_agent**: Generates 5 platform-optimized hooks per platform
3. **li_content_writer_agent**: Creates LinkedIn content, selects best hook
4. **x_content_writer_agent**: Creates ultra-dense Twitter/X content (≤280 chars)
5. **fact_checker_agent**: Ensures perfect accuracy (10/10 required)
6. **voice_checker_agent**: Applies FAR.AI brand voice + maximum conciseness
7. **compliance_auditor_agent**: Style compliance + final content assembly

### Key Design Principles

**Quality Standards**: Perfect accuracy (10/10), FAR.AI brand voice (not speaker mimicry), maximum conciseness, strict style compliance (14/14).

**Content Flow**: Generate multiple options → select best → quality control → assemble final posts → update Coda database.

**Webhook Integration**: Coda triggers processing automatically, system updates status and results back to database.

## Environment Requirements

### Required Environment Variables
Create `.env` file with:
```
CODA_API_TOKEN=your_coda_token
OPENAI_API_KEY=your_openai_key  # If using OpenAI models
ANTHROPIC_API_KEY=your_anthropic_key  # For Claude models
```

### Model Configuration
Default LLM: `anthropic/claude-opus-4-20250514` (configured in crew classes)

## Content Generation Process

### Input Data Structure
```python
class TalkRequest(BaseModel):
    speaker: str
    title: str
    event: str
    affiliation: str
    yt_full_link: str | HttpUrl
    resource_url: str | HttpUrl | None
    transcript: str
```

### Webhook Endpoints
- `/coda_webhook/{function_name}` - Generic webhook handler
- `/promote_talk` - Direct API endpoint
- Function names: `promote_talk`, `promote_research`, `promote_event`

### Output Columns (Coda)
- "Hooks (AI)" - Selected LinkedIn hook
- "LI content" - Assembled LinkedIn post with bullets and CTA
- "X content" - Final Twitter/X content with links
- "Progress" - Status updates and error messages
- "Eval notes" - Quality assessment and rubric breakdown

## Style Guide Integration

The system automatically loads style guides from `docs/` and passes them to agents:
- `style_shared.md` - Cross-platform voice and tone
- `style_li.md` - LinkedIn-specific formatting and examples
- `style_x.md` - Twitter/X ultra-dense content requirements

Style guides include high-performing content examples that agents learn from during generation.