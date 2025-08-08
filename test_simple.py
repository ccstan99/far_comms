#!/usr/bin/env python
"""
Simple test of existing functions - just provide your actual values and run:
PYTHONPATH=src python test_simple.py
"""

import asyncio
from src.far_comms.main import get_coda_data
from src.far_comms.tools.coda_tool import CodaTool

# TODO: Replace with your actual values from logs
DOC_ID = "Jv4r8SGAJp"
THIS_ROW = "grid-LcVoQIcUB2/i-AbYMTOZsbA"  # e.g. "grid-abc123/i-HvvZPCM8XO"

async def test_existing_functions():
    print("Testing your existing functions...")
    
    # Test 1: Use your get_coda_data function
    print("1. Testing get_coda_data...")
    coda_ids, talk_data = await get_coda_data(THIS_ROW, DOC_ID)
    print(f"✅ Read data: {talk_data.speaker} - {talk_data.title}")
    
    # Test 2: Use your CodaTool update function with sample crew output
    print("2. Testing CodaTool.update_rows...")
    coda_tool = CodaTool()
    
    # Real crew output data from your last run
    import json
    crew_output = {
        "li_hook": "40 persuasion tactics crack AI safety—with near 90% success.",
        "paragraph_summary": "Northeastern's Weiyan Shi discovered AI's vulnerability: social science persuasion beats technical attacks. Her team's 40-strategy framework breaks safety guardrails systematically. The twist? Advanced models fail more because they understand persuasion better. Claude uniquely resists where GPT-4 falls.",
        "bullets": [
            "▸ Smarter AI = easier targets",
            "▸ Claude blocks attacks GPT fails", 
            "▸ Dialogue flips core beliefs",
            "▸ Social science beats hacking"
        ],
        "x_content": "Social science cracks AI safety: 40 persuasion tactics achieve near 90% jailbreak success, beating technical attacks. Why? Smarter models understand—and fall for—manipulation. GPT-4 vulnerable, Claude resistant. Multi-turn dialogue even flips beliefs about basic facts. 👇\n---\n▶️ Watch Singapore Alignment Workshop recording: [video_url]\n📄 Read paper: [resource_url]",
        "publication_decision": "APPROVED",
        "final_quality_score": 14,
        "eval_notes": "Content Quality (8/8): Hook Strength 2/2 - counterintuitive finding about AI vulnerability..."
    }
    
    # Simulate the same updates your main.py would do
    sample_updates = [{
        "row_id": coda_ids.row_id,
        "updates": {
            "Summaries status": "Done",
            "Progress": json.dumps(crew_output, indent=2),
            "Paragraph (AI)": crew_output["paragraph_summary"],
            "Hooks (AI)": crew_output["li_hook"],
            "LI content": crew_output["li_hook"],  # Simple test - just use hook
            "X content": crew_output["x_content"],  # This is the key test!
            "Eval notes": crew_output["eval_notes"]
        }
    }]
    
    result = coda_tool.update_rows(coda_ids.doc_id, coda_ids.table_id, sample_updates)
    print(f"✅ Update result: {result}")

if __name__ == "__main__":
    asyncio.run(test_existing_functions())