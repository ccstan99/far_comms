# FAR.AI Communications System

Multi-agent AI system powered by [crewAI](https://crewai.com) for processing academic talk content and generating high-quality social media content for FAR.AI. The system uses specialized agent crews for content processing, analysis, and social media generation.

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
- **POST** `/coda_webhook/prepare_talk` - Process slides and transcripts
- **POST** `/coda_webhook/promote_talk` - Generate social media content
- **POST** `/promote_talk` - Direct API endpoint for content generation

### Alternative: Direct Crew Execution
```bash
# Deprecated - use FastAPI endpoints instead
uv run far_comms
```

## System Architecture

### Multi-Agent Crews

**PrepareTalkCrew**: 4-agent pipeline for content processing
1. **Slide Processor** - Extracts slide content, identifies resources
2. **Transcript Processor** - Refines AI transcripts with technical accuracy  
3. **Resource Researcher** - Finds URLs for papers and social media
4. **Final Assembly** - Assembles content for database update

**PromoteTalkCrew**: 7-agent pipeline for social media generation  
1. **Transcript Analyzer** - Preserves speaker content structure
2. **Hook Specialist** - Generates platform-optimized hooks
3. **LinkedIn Writer** - Creates LinkedIn content
4. **Twitter/X Writer** - Creates ultra-dense tweets (≤280 chars)
5. **Fact Checker** - Ensures perfect accuracy (10/10)
6. **Voice Checker** - Applies FAR.AI brand voice
7. **Compliance Auditor** - Final style compliance and assembly

### Key Features
- **Multimodal PDF processing** with QR code extraction
- **Video transcript processing** via AssemblyAI
- **Academic resource research** across multiple databases
- **Social media content optimization** for LinkedIn and Twitter/X
- **Coda database integration** with webhook automation

## Configuration

See `CLAUDE.md` for detailed configuration instructions, including:
- Agent and task YAML configurations
- Style guide integration
- Model configurations (Claude 4 Sonnet/Opus)
- Environment variables and API keys

## Directory Structure
```
src/far_comms/
├── crews/                    # Agent crews and configurations
│   ├── config/              # YAML agent and task definitions
│   ├── prepare_talk_crew.py # Content processing crew
│   └── promote_talk_crew.py # Social media generation crew
├── handlers/                # Webhook and API request handlers  
├── utils/                   # Content preprocessing and utilities
├── tools/                   # Coda integration and custom tools
└── main.py                  # FastAPI application entry point
```
