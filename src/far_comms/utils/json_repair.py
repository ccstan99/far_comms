#!/usr/bin/env python

import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def json_repair(result_text: str, max_attempts: int = 3, fallback_value: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Iteratively repair malformed JSON using json-repair library and Claude Haiku until valid.
    
    Args:
        result_text: Raw text that should contain JSON
        max_attempts: Maximum repair attempts (default: 3)
        fallback_value: Dict to return if all repair attempts fail (default: empty dict)
    
    Returns:
        Parsed JSON dict, or fallback_value if repair fails
    """
    
    def extract_json_from_markdown(text: str) -> str:
        """Extract JSON from markdown code blocks"""
        if text.strip().startswith('```json'):
            json_start = text.find('{')
            json_end = text.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                return text[json_start:json_end]
        return text.strip()
    
    def cleanup_with_haiku(malformed_json: str) -> str:
        """Use Haiku to clean up malformed JSON"""
        try:
            from anthropic import Anthropic
            import os
            
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY not available for Haiku JSON cleanup")
                return malformed_json
            
            client = Anthropic(api_key=api_key)
            
            prompt = f"""Fix this malformed JSON to be valid JSON. Return ONLY the corrected JSON with no markdown formatting or extra text:

{malformed_json}"""
            
            response = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            cleaned = response.content[0].text.strip()
            
            # Clean any potential markdown formatting from response
            if cleaned.startswith('```json'):
                cleaned = extract_json_from_markdown(cleaned)
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:].strip()
                if cleaned.endswith('```'):
                    cleaned = cleaned[:-3].strip()
            
            return cleaned
        except Exception as e:
            logger.warning(f"Haiku cleanup failed: {e}")
            return malformed_json
    
    # Start with the original text
    current_text = extract_json_from_markdown(result_text)
    
    # Quick fix for incomplete JSON objects (missing wrapping braces)
    stripped = current_text.strip()
    if (stripped.startswith('"') and not stripped.startswith('{')) or \
       (stripped.endswith('}') and not stripped.startswith('{')):
        logger.debug("Detected incomplete JSON object, wrapping with {}")
        current_text = '{' + stripped + '}'
    
    for attempt in range(max_attempts):
        logger.debug(f"JSON repair attempt {attempt + 1}/{max_attempts}")
        
        # Try parsing as-is
        try:
            parsed = json.loads(current_text)
            logger.info(f"Successfully parsed JSON on attempt {attempt + 1}")
            return parsed
        except json.JSONDecodeError as e:
            logger.debug(f"Attempt {attempt + 1} failed: {e}")
            
            # Try json-repair library first
            try:
                import json_repair as repair_lib
                repaired_text = repair_lib.repair_json(current_text)
                parsed = json.loads(repaired_text)
                logger.info(f"Successfully repaired JSON with json-repair on attempt {attempt + 1}")
                return parsed
            except (ImportError, Exception) as repair_error:
                logger.debug(f"json-repair failed on attempt {attempt + 1}: {repair_error}")
            
            # If json-repair failed or isn't available, try Haiku cleanup
            if attempt < max_attempts - 1:  # Don't use Haiku on the last attempt
                logger.debug(f"Trying Haiku cleanup on attempt {attempt + 1}")
                current_text = cleanup_with_haiku(current_text)
    
    # All attempts failed, return fallback or empty dict
    logger.warning(f"All {max_attempts} JSON repair attempts failed")
    return fallback_value or {}