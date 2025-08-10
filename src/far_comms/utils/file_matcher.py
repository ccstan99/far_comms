#!/usr/bin/env python

import re
import os
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


def clean_name(name: str) -> str:
    """Remove all non-alphanumeric characters and convert to lowercase"""
    return re.sub(r'[^a-zA-Z0-9]', '', name.lower())


def score_filename_match(speaker_parts: List[str], filename: str) -> Tuple[int, int, str]:
    """
    Score how well speaker name matches filename
    
    Args:
        speaker_parts: List of name parts (e.g., ["Xiaoyuan", "Yi"])
        filename: Filename to match against
    
    Returns:
        Tuple of (score, specificity, match_description)
    """
    clean_filename = clean_name(filename)
    first_name = clean_name(speaker_parts[0]) if speaker_parts else ""
    last_name = clean_name(speaker_parts[-1]) if len(speaker_parts) > 1 else ""
    
    # Full name exact match (highest score)
    full_name = "".join(clean_name(part) for part in speaker_parts)
    if full_name in clean_filename:
        return (100, len(full_name), f"full_exact:{full_name}")
    
    # First + Last exact match - but check specificity
    if first_name and last_name and first_name in clean_filename and last_name in clean_filename:
        # Higher specificity for longer names and both names present
        specificity = len(first_name) + len(last_name)
        return (90, specificity, f"both_exact:{first_name}+{last_name}")
    
    # Check for partial first name match + exact last name match
    # This handles cases like "Xiaoyuan Yi" vs filenames with "Xiaoyun Yi" vs "Yinpeng Dong"
    if first_name and last_name and last_name in clean_filename:
        # Look for partial first name matches
        first_similarity = 0
        if len(first_name) >= 4:
            for i in range(min(len(first_name), 8), 3, -1):  # Check longer substrings first
                if first_name[:i] in clean_filename:
                    first_similarity = i
                    break
        
        if first_similarity >= 4:  # Minimum 4 chars for partial match
            # Bonus for having both partial first + exact last
            specificity = first_similarity + len(last_name)
            return (85, specificity, f"partial_first_exact_last:{first_name[:first_similarity]}+{last_name}")
    
    # Single name exact match - prefer longer, more specific names
    best_single_score = 0
    best_specificity = 0
    best_description = ""
    
    if first_name and first_name in clean_filename:
        best_single_score = 80
        best_specificity = len(first_name)
        best_description = f"first_exact:{first_name}"
    
    if last_name and last_name in clean_filename:
        if 80 > best_single_score or (80 == best_single_score and len(last_name) > best_specificity):
            best_single_score = 80
            best_specificity = len(last_name)
            best_description = f"last_exact:{last_name}"
    
    if best_single_score > 0:
        return (best_single_score, best_specificity, best_description)
    
    # Long partial matches (6+ chars) - prefer longer matches
    best_partial_score = 0
    best_partial_specificity = 0
    best_partial_description = ""
    
    if len(first_name) >= 6 and first_name[:6] in clean_filename:
        best_partial_score = 60
        best_partial_specificity = 6
        best_partial_description = f"first_partial:{first_name[:6]}"
        
    if len(last_name) >= 6 and last_name[:6] in clean_filename:
        if 60 > best_partial_score or (60 == best_partial_score and 6 > best_partial_specificity):
            best_partial_score = 60
            best_partial_specificity = 6
            best_partial_description = f"last_partial:{last_name[:6]}"
    
    if best_partial_score > 0:
        return (best_partial_score, best_partial_specificity, best_partial_description)
    
    # Medium partial matches (4-5 chars)
    if len(first_name) >= 5 and first_name[:4] in clean_filename:
        return (40, 4, f"first_medium:{first_name[:4]}")
    if len(last_name) >= 5 and last_name[:4] in clean_filename:
        return (40, 4, f"last_medium:{last_name[:4]}")
    
    return (0, 0, "no_match")


def find_best_matching_file(speaker_name: str, file_paths: List[str], min_score: int = 40) -> Optional[str]:
    """
    Find the best matching file for a speaker name
    
    Args:
        speaker_name: Speaker name to match
        file_paths: List of file paths to search through
        min_score: Minimum score required for a match (default: 40)
    
    Returns:
        Path to best matching file or None if no good match found
    """
    speaker_parts = speaker_name.strip().split()
    if not speaker_parts:
        return None
    
    # Score all files and find best match
    best_score = 0
    best_specificity = 0
    best_match = None
    best_description = ""
    
    for file_path in file_paths:
        filename = os.path.basename(file_path)
        score, specificity, description = score_filename_match(speaker_parts, filename)
        
        # Better match if higher score, or same score but more specific
        if (score > best_score or 
            (score == best_score and specificity > best_specificity)):
            best_score = score
            best_specificity = specificity
            best_match = file_path
            best_description = description
    
    if best_match and best_score >= min_score:
        logger.info(f"Matched '{speaker_name}' to '{os.path.basename(best_match)}' via: {best_description} (score: {best_score}, specificity: {best_specificity})")
        return best_match
    
    logger.warning(f"No good file match found for '{speaker_name}' (best score: {best_score})")
    return None


# Example usage and testing
if __name__ == "__main__":
    # Test with sample filenames
    test_files = [
        "16_Yinpeng_Dong.mp4",
        "17_Xiaoyun_Yi.mp4", 
        "4_Animesh_Mukherjee.mp4"
    ]
    
    test_speakers = [
        "Xiaoyuan Yi",
        "Xiaoyun Yi",
        "Yinpeng Dong", 
        "Animesh Mukherjee"
    ]
    
    print("Testing file matching:")
    for speaker in test_speakers:
        match = find_best_matching_file(speaker, test_files)
        result = os.path.basename(match) if match else "No match"
        print(f"  {speaker:20} → {result}")