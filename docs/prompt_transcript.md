# Transcript Processing Instructions

## Overview
These instructions define how to process video transcripts from AssemblyAI output to prepare them for publication or further use.

## Style Guidelines

### Language and Standards
- **American English** (not British English)
- **IEEE Style Guide** for technical writing conventions
- **Merriam-Webster** spelling as the authoritative source

### AI Model Names
Ensure correct spelling and formatting of AI model names:
- Claude 3(.5/.6/.7) (Opus/Sonnet/Haiku)
- GPT-4o (mini)
- o1, o3, o4 (with optional -mini suffix)
- AlphaEvolve
- Pythia #B (e.g., Pythia 12B)
- Mistral large #B, Mistral medium #B, Mistral small #B (e.g., Mistral medium 2.7B)
- Llama3 #B, Llama3.1 #B (e.g., Llama3 70B)
- Qwen #B (e.g., Qwen 7B)

**Important**: For parameter counts, ensure NO space between number and "B" (correct: "70B", incorrect: "70 B")

### Hyphenated Terms
These terms must always be hyphenated:
- pre-train (and derivatives: pre-training, pre-trained)
- fine-tune (and derivatives: fine-tuning, fine-tuned)
- in-context learning
- out-of-context learning
- chain-of-thought (CoT) reasoning
- white-box
- black-box
- pre- and post-mitigation
- open-weights
- 0-shot prompting
- 1-shot prompting
- few-shot prompting

### Specialized Terms
Ensure correct spelling and formatting:
- red teaming (two words, no hyphen)
- Codes of Practice (capitalized)
- data set (two words)
- sysadmin (one word)
- Redwood Research (proper noun, both words capitalized)
- Execute Replace Audit Framework (all words capitalized)

## Processing Steps

1. **Spelling Correction**: Fix common transcription errors while maintaining technical accuracy
2. **Formatting**: Apply consistent formatting for model names and technical terms
3. **Grammar**: Correct grammar issues typical in speech-to-text conversion
4. **Punctuation**: Add or correct punctuation for readability
5. **Capitalization**: Ensure proper capitalization of proper nouns and sentence beginnings

## Output Requirements

### Corrected Text
- Clean, proofread version of the transcript
- All corrections applied according to these guidelines
- Maintains the original meaning and technical accuracy

### Diff Report
When requested, provide:
- Context around each change (approximately 10-15 words before and after)
- Clear indication of what was changed
- Reason for the change (if not obvious)

## Common Transcription Errors to Watch For

1. **Homophones**: "there/their/they're", "to/too/two", "your/you're"
2. **Technical terms**: Often transcribed phonetically rather than correctly
3. **Punctuation**: Speech often lacks clear punctuation markers
4. **Run-on sentences**: Natural speech patterns create long, unpunctuated segments
5. **Filler words**: "um", "uh", "you know" - remove unless contextually important
6. **False starts**: Speaker corrections mid-sentence - clean up for readability

## Quality Checks

Before finalizing:
1. Verify all AI model names are correctly formatted
2. Confirm hyphenated terms are consistent throughout
4. Ensure American English spelling throughout
5. Validate technical terms against the specialized vocabulary list
