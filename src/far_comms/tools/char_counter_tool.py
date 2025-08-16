from crewai.tools import BaseTool


class CharacterCounterTool(BaseTool):
    name: str = "character_counter"
    description: str = "Count characters in text and check if it fits within Twitter/X 280-character limit. Use this to verify social media content length before finalizing."

    def _run(self, text: str) -> str:
        """
        Count characters in text and check Twitter/X limit compliance
        
        Args:
            text: The text content to analyze
            
        Returns:
            Formatted string with character count and limit status
        """
        if not text:
            return "Error: No text provided to count"
        
        char_count = len(text)
        twitter_limit = 280
        
        if char_count <= twitter_limit:
            remaining = twitter_limit - char_count
            return f"✓ {char_count}/280 characters ({remaining} remaining) - Within Twitter/X limit"
        else:
            overflow = char_count - twitter_limit
            return f"✗ {char_count}/280 characters ({overflow} over limit) - EXCEEDS Twitter/X limit, needs shortening"