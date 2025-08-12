# TODO: PrepareTalkCrew Refactoring

## ✅ COMPLETED (August 2025)
**Status**: All prepare_talk refactoring completed on `prep-talk-refinements` branch

### ✅ Phase 1: Testing & Validation - DONE
- ✅ Tested slides extraction with visual elements preservation
- ✅ Tested transcript processing with AssemblyAI  
- ✅ Verified speaker validation logic with smart title case
- ✅ Confirmed immediate Coda updates working properly
- ✅ Tested JSON parsing and error handling

### ✅ Phase 2: CrewAI → Python Refactoring - DONE
**Implementation**: `src/far_comms/handlers/prepare_talk_simple.py` (689 lines)

- ✅ **Slides Processing**: Replaced with direct Claude-Sonnet-4 calls
  - Visual elements preservation (QR codes, images, charts, tables)
  - Smart speaker validation preventing data overwrites
  - Immediate Coda updates after processing
  
- ✅ **Transcript Processing**: Replaced with direct Claude calls  
  - Verbatim content preservation with SRT reconstruction
  - Technical term correction using slide context
  - Conservative validation with placeholder detection

### ✅ Benefits Achieved
- ✅ Easier debugging (689 lines vs 1000+ CrewAI code)
- ✅ Direct LLM control with robust JSON parsing
- ✅ Simplified architecture (no CrewAI complexity)
- ✅ Superior quality vs original system

### ✅ Final Architecture Implemented
```
prepare_talk() → 
  ├── process_slides() → Claude-Sonnet-4 → immediate Coda update
  └── process_transcript() → Claude-Sonnet-4 → immediate Coda update
```

**Files**: Conservative cleanup removed 1,089 lines of obsolete CrewAI code while preserving important utilities (content_preprocessor.py, visual_analyzer.py, slide_formatter.py, transcript_cleaner.py).

# TODO: Research Analysis System

## Current Status
The research analysis system (`analyze_research.py`) is now functional and merged to main with core issues resolved:
- ✅ Fixed section-by-section LLM processing (no more truncation)
- ✅ Eliminated LLM hallucination of fake figures and content expansion  
- ✅ Added proper abstract extraction from PyMuPDF4LLM
- ✅ Removed duplicate title/authors sections
- ✅ H2+H3 section grouping working properly

## Phase 1: Content Quality Improvements
- [ ] **Fix author parsing** - Some names are merged together (e.g. "Jean-Francois Godbout Thomas Costello")
- [ ] **Parse actual affiliations** - Currently showing placeholder text instead of real institutions
- [ ] **Improve figure integration** - Add better alt text descriptions based on actual figure content
- [ ] **Add author handle lookup** - Use promote_talk Coda table to find social media handles for researchers

## Phase 2: System Integration  
- [ ] **Full promote_research system** - Complete pipeline for blog posts, animations, and social media content generation from research papers
- [ ] **Quality validation** - Ensure research analysis output meets standards for social media content generation

## Architecture Notes
The current system uses direct Python + LLM calls (Claude Sonnet) for section processing, which works well for the small team. This approach should be maintained for consistency with the overall architecture vision above.