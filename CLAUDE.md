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
- `PromoteTalkCrew`: 7-agent pipeline for social media content generation
- `PrepareTalkCrew`: 4-agent pipeline for slide/transcript processing and resource extraction
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

### Agent Architecture

**PromoteTalkCrew (Social Media Content)**
7-agent sequential pipeline for social media content generation:
1. **transcript_analyzer_agent**: Preserves speaker's original content and structure
2. **hook_specialist_agent**: Generates 5 platform-optimized hooks per platform
3. **li_content_writer_agent**: Creates LinkedIn content, selects best hook
4. **x_content_writer_agent**: Creates ultra-dense Twitter/X content (≤280 chars)
5. **fact_checker_agent**: Ensures perfect accuracy (10/10 required)
6. **voice_checker_agent**: Applies FAR.AI brand voice + maximum conciseness
7. **compliance_auditor_agent**: Style compliance + final content assembly

**PrepareTalkCrew (Content Processing)**
4-agent sequential pipeline for slide/transcript processing:
1. **slide_processor_agent**: Extracts and cleans slide content, identifies resources
2. **transcript_processor_agent**: Refines AI-generated transcripts with technical accuracy
3. **resource_researcher_agent**: Finds URLs for academic papers and social media posts
4. **final_assembly_agent**: Assembles processed content for Coda database update

### Key Design Principles

**Quality Standards**: Perfect accuracy (10/10), FAR.AI brand voice (not speaker mimicry), maximum conciseness, strict style compliance (14/14).

**Content Flow**: Generate multiple options → select best → quality control → assemble final posts → update Coda database.

**Webhook Integration**: Coda triggers processing automatically, system updates status and results back to database.

## Environment Requirements

### Required Environment Variables
Create `.env` file with:
```
CODA_API_TOKEN=your_coda_token
ANTHROPIC_API_KEY=your_anthropic_key  # For Claude models
ASSEMBLYAI_API_KEY=your_assemblyai_key  # For transcript processing
SERPER_API_KEY=your_serper_key  # For web research (optional)
```

### Model Configuration
**PromoteTalkCrew**:
- Claude 4.1 Opus: `claude-opus-4-1-20250805` (content creation, final review)
- Claude 4 Sonnet: `claude-sonnet-4-20250514` (analysis, systematic tasks)

**PrepareTalkCrew**:
- Claude 4 Sonnet: `claude-sonnet-4-20250514` (all processing tasks)

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
- `/promote_talk` - Social media content generation
- `/prepare_talk` - Slide/transcript processing
- Function names: `promote_talk`, `prepare_talk`, `promote_research`, `promote_event`

### Output Columns (Coda)

**PromoteTalkCrew**:
- "Hooks (AI)" - Selected LinkedIn hook
- "LI content" - Assembled LinkedIn post with bullets and CTA
- "X content" - Final Twitter/X content with links
- "Progress" - Status updates and error messages
- "Eval notes" - Quality assessment and rubric breakdown

**PrepareTalkCrew**:
- "Slides" - Processed slide content with visual elements marked
- "Resources" - Academic papers and social media posts with URLs
- "SRT" - Timestamped transcript in SRT format
- "Transcript" - Clean formatted transcript paragraphs
- "Webhook progress" - Processing status and statistics
- "Webhook status" - Done/Failed status

## Style Guide Integration

The system automatically loads style guides from `docs/` and passes them to agents:

**PromoteTalkCrew**:
- `style_shared.md` - Cross-platform voice and tone
- `style_li.md` - LinkedIn-specific formatting and examples
- `style_x.md` - Twitter/X ultra-dense content requirements

**PrepareTalkCrew**:
- `prompt_transcript.md` - Transcript processing style guide (IEEE standards, AI model names, hyphenation rules)

Style guides include high-performing content examples and technical formatting standards that agents learn from during generation.

## Content Processing Features

### Multimodal PDF Analysis
- Extracts text content using PyPDFLoader
- Analyzes visual elements (charts, diagrams, images) with Claude multimodal
- QR code detection and URL extraction using pyzbar library
- Combines text and visual descriptions for comprehensive slide processing

### Video Transcript Processing
- AssemblyAI integration for speech-to-text transcription
- Local video file processing and YouTube URL fallback (with yt-dlp)
- SRT format preservation with timestamp reconstruction
- Technical term correction using slide context for accuracy
- Verbatim content preservation (95-105% word count retention)

### Resource Research
- Academic paper URL resolution from incomplete citations
- arXiv, ACM Digital Library, IEEE Xplore database searching
- Social media post discovery (Twitter/X, LinkedIn) for amplification opportunities
- QR code URL validation and metadata extraction
- When error encountered, webhook status in coda should be "Error" not Failed. Valid options: Error, Done, Not started, In progress
- don't overcomplicate or overengineer code
- all api keys in .env
- tasks.yaml instruction markers around long input with XML tags <CONTENT>{...}</CONTENT}