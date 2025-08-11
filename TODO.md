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