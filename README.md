# FAR.AI Communications System

Multi-agent AI system powered by [crewAI](https://crewai.com) for processing academic content and generating high-quality social media content for FAR.AI. The system handles talk transcripts, research papers, and event content using specialized agent crews and streamlined processing pipelines.

## Installation

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys:
# CODA_API_TOKEN=your_coda_token
# ANTHROPIC_API_KEY=your_anthropic_key
# ASSEMBLYAI_API_KEY=your_assemblyai_key
# SERPER_API_KEY=your_serper_key (optional)
```

### System Dependencies

**For QR code processing:**
```bash
# macOS
brew install zbar

# Ubuntu/Debian
apt-get install libzbar0

# Windows
# Download and install zbar from: http://zbar.sourceforge.net/download.html
```

## Running the System

### FastAPI Server (Recommended)
```bash
# Activate environment
conda activate llm-agents

# Start FastAPI server with proper Python path
PYTHONPATH=src uvicorn far_comms.main:app --reload

# Optional: Expose server for webhook testing
cloudflared tunnel --url http://localhost:8000
```

### Available Endpoints

**Coda Webhook Integration:**
- **POST** `/coda_webhook/{function_name}` - Generic webhook handler for all functions
- **POST** `/run_event/{function_name}/{table_id}/{doc_id}` - Batch processing endpoint

**Direct API Endpoints:**
- **POST** `/promote_talk` - Generate social media content for talks
- **POST** `/analyze_research` - Process research papers
- **POST** `/assemble_socials` - Assemble final social media posts with templates

**Supported Functions:**
- `promote_talk` - 7-agent social media content generation
- `prepare_talk` - Slide/transcript processing (streamlined handler)
- `promote_research` - Research paper analysis and promotion
- `promote_event` - Event content generation
- `assemble_socials` - Template-based social media assembly

### Alternative: Direct Crew Execution
```bash
# Deprecated - use FastAPI endpoints instead
uv run far_comms
```

## System Architecture

### Content Processing Architecture

**PromoteTalkCrew**: 7-agent pipeline for social media generation  
1. **Transcript Analyzer** - Preserves speaker content structure
2. **Hook Specialist** - Generates platform-optimized hooks (5 options per platform)
3. **LinkedIn Writer** - Creates LinkedIn content with bullets and CTA
4. **Twitter/X Writer** - Creates ultra-dense tweets (≤280 chars)
5. **Fact Checker** - Ensures perfect accuracy (10/10 required)
6. **Voice Checker** - Applies FAR.AI brand voice + maximum conciseness
7. **Compliance Auditor** - Final style compliance and assembly

**Streamlined Processing Handlers**:
- **prepare_talk** - Direct slide/transcript processing with multimodal PDF analysis
- **analyze_research** - Research paper analysis with academic database integration
- **assemble_socials** - Template-based social media post assembly with platform-specific formatting

**Additional Crews**:
- **PromoteResearchCrew** - Research paper promotion and analysis
- **PromoteEventCrew** - Event content generation and social media planning

### Key Features
- **Multimodal PDF processing** with QR code extraction and visual analysis
- **Video transcript processing** via AssemblyAI with SRT format support
- **Academic resource research** across arXiv, ACM, IEEE databases
- **Social media template system** with platform-specific formatting
- **Background task execution** with real-time progress tracking
- **Coda database integration** with webhook automation and batch processing
- **PPTX to PDF conversion** for comprehensive slide processing

## Configuration

See `CLAUDE.md` for detailed configuration instructions, including:
- Agent and task YAML configurations
- Style guide integration
- Model configurations (Claude 4 Sonnet/Opus)
- Environment variables and API keys

## Directory Structure
```
src/far_comms/
├── crews/                          # Agent crews and configurations
│   ├── config/                     # YAML agent and task definitions
│   │   ├── promote_talk/           # Social media generation crew config
│   │   ├── promote_research/       # Research promotion crew config  
│   │   └── promote_event/          # Event promotion crew config
│   ├── promote_talk_crew.py        # 7-agent social media generation
│   ├── promote_research_crew.py    # Research paper promotion
│   └── promote_event_crew.py       # Event content generation
├── handlers/                       # Processing handlers and webhook endpoints
│   ├── promote_talk.py             # Social media content generation
│   ├── prepare_talk.py             # Slide/transcript processing
│   └── analyze_research_handler.py # Research paper analysis
├── utils/                          # Content processing utilities
│   ├── coda_client.py              # Coda database integration
│   ├── slide_processor.py          # Multimodal PDF processing
│   ├── transcript_processor.py     # Video transcript processing
│   ├── social_assembler.py         # Template-based post assembly
│   └── content_preprocessor.py     # File matching and conversion
├── tools/                          # Custom CrewAI tools
│   ├── char_counter_tool.py        # Character counting for social limits
│   └── custom_tool.py              # Base tool classes
├── models/                         # Pydantic request/response models
└── main.py                         # FastAPI application with webhook handling
```

## Template System

The system uses markdown templates in `docs/` for consistent social media formatting:

```
docs/
├── assemble_socials.md       # Social media template system
├── style_shared.md           # Cross-platform voice and tone
├── style_LI.md               # LinkedIn-specific formatting
└── style_X.md                # Twitter/X ultra-dense requirements
```
