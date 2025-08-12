# TODO: PrepareTalkCrew Refactoring

## Current Status
The prepare_talk function has been updated with Python-based validation logic and optimized Coda batching, but **needs thorough testing for slides & transcript extraction** before proceeding with the next phase.

## Phase 1: Testing & Validation ⚠️ REQUIRED
- [ ] Test slides extraction with various PDF formats
- [ ] Test transcript processing with different video sources  
- [ ] Verify speaker validation logic works correctly across edge cases
- [ ] Confirm Coda batching (main content + optional validation) functions properly
- [ ] Test AssemblyAI caching and error handling

## Phase 2: CrewAI → Python Refactoring
Once Phase 1 testing is complete, refactor the system:

### Replace CrewAI with Direct LLM Calls
- [ ] **Slides Processing**: Convert `slide_processor_agent` to Python function calling Claude directly
  - Use similar instructions as current agent task descriptions
  - Keep multimodal PDF analysis and QR code extraction
  - Maintain speaker validation logic in Python post-processing
  
- [ ] **Transcript Processing**: Convert `transcript_processor_agent` to Python function calling Claude directly  
  - Use similar instructions for verbatim preservation (95-105% word count)
  - Keep SRT reconstruction and technical term correction
  - Maintain paragraph formatting logic

### Benefits of Python Approach
- Easier debugging and maintenance for 2-3 person comms team
- More direct control over LLM prompts and error handling
- Simpler architecture without CrewAI complexity
- Faster iteration and testing cycles

### Final Step
- [ ] **Merge analyze_task back into prepare_task**: Once slides/transcript are direct Python+LLM calls, combine with resource research and analysis for single comprehensive processing function

## Architecture Vision
```
prepare_talk() → 
  ├── extract_slides_content(pdf_path, speaker_name) → Claude call
  ├── process_transcript_content(transcript_raw, slides_context) → Claude call  
  ├── research_resources(slides_content, transcript_content) → Claude call
  └── update_coda_with_all_content()
```

This maintains the current quality and functionality while being more maintainable for a small team.

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