# Outstanding Tasks

## Promote Events / Talks

### Current Focus: Transcript Analysis Testing
- [ ] **Test transcript analyzer in isolation** - Verify markdown output quality and speaker voice preservation
- [ ] **Validate Coda Analysis column integration** - Ensure markdown storage and retrieval works

### Future Architecture: Dispatcher-Based Crew
**Vision**: `promote_talk_crew` with smart orchestration
```
promote_talk_crew:
├── dispatcher_agent (checks what's needed)
├── resource_researcher_agent (if Resources empty)  
├── transcript_analyzer_agent (if Analysis empty)
├── content_creator_agent
├── fact_checker_agent
└── final_assembly_agent
```

**Benefits**: Dynamic workflow, only runs needed components, single crew for all promotion

### Testing Strategy
1. **Phase 1**: Test individual agents in isolation (current)
2. **Phase 2**: Integration testing with dispatcher
3. **Phase 3**: Full promote_talk crew with content generation

### Backlog
- [ ] **Image-rich slide detection** - Check how image-rich slides are identified and handled
- [ ] **Human-in-the-loop social media** - Allow for iterating on drafted social media content to incorporate human feedback or additional LLM refinement
- [ ] **Merge analyze_talk** - Integrate analyze_talk functionality into prepare_talk when preprocessing logic is stable
- [ ] **Social media research agent** - Optional second agent for analyze_talk crew to find social media posts about discovered resources (Option A implementation)

### Social Media Research Agent Details (Future)

**Role**: Social Media Post Detective - finds verified posts by speaker/co-authors about specific resources  
**Dependencies**: Must run AFTER resource_researcher_agent finds core resources  
**Tools**: SerperSearchResults + SocialMediaLookupTool (read-only Coda contacts for X/Twitter/LinkedIn/Bluesky)  
**Validation**: Posts must reference specific resource titles/URLs found in step 1, no generic posts  
**Search Strategy**: Get speaker+co-author handles → search for posts mentioning exact resources → cross-validate content  
**Benefits**: Separation of concerns, better validation, optional (can disable without affecting core)  
**When**: After core resource research is stable, if social media discovery becomes important

## Promote Research

- [ ] **Fix author parsing** - Some names are merged together (e.g. "Jean-Francois Godbout Thomas Costello")
- [ ] **Parse actual affiliations** - Currently showing placeholder text instead of real institutions
- [ ] **Improve figure integration** - Add better alt text descriptions based on actual figure content
- [ ] **Add author handle lookup** - Use promote_talk Coda table to find social media handles for researchers
- [ ] **Full promote_research system** - Complete pipeline for blog posts, animations, and social media content generation from research papers
- [ ] **Quality validation** - Ensure research analysis output meets standards for social media content generation

## Other Tasks

- [ ] **Add promote_event support** - Complete implementation for event promotion function
- [ ] **Add promote_job support** - Implement support for job posting promotion function
- [ ] **Add publish_socials support** - Upload LinkedIn, X, Bsky to Buffer
