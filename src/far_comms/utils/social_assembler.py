#!/usr/bin/env python

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def assemble_socials(crew_output: dict, coda_data: dict) -> dict:
    """
    Assemble platform-specific social media posts from crew output and Coda data
    
    Args:
        crew_output: Parsed output from promote_talk crew (contains li_content, x_content, resources)
        coda_data: Input data from Coda (contains event_name, yt_full_link, etc.)
    
    Returns:
        dict: {"LI post": str, "X post": str, "Bsky post": str}
    """
    try:
        # Extract content from crew output
        li_content = crew_output.get("LI content", "").strip()
        x_content = crew_output.get("X + Bsky content", "").strip()
        resources = crew_output.get("Resources", "").strip()
        
        # Extract metadata from Coda data
        event_name = coda_data.get("event_name", coda_data.get("event", "")).strip()
        yt_full_link = coda_data.get("yt_full_link", "").strip()
        
        logger.info(f"Assembling socials - Event: {event_name}, Resources: {bool(resources)}, Video: {bool(yt_full_link)}")
        
        # Assemble LinkedIn post
        li_post = _assemble_linkedin_post(li_content, event_name, yt_full_link, resources)
        
        # Assemble X/Twitter post  
        x_post = _assemble_x_post(x_content, event_name, yt_full_link, resources)
        
        # Assemble Bluesky post (same format as X)
        bsky_post = _assemble_bsky_post(x_content, event_name, yt_full_link, resources)
        
        result = {
            "LI post": li_post,
            "X post": x_post,  
            "Bsky post": bsky_post
        }
        
        logger.info(f"Successfully assembled {len(result)} social media posts")
        return result
        
    except Exception as e:
        logger.error(f"Error assembling social media posts: {e}")
        # Return empty posts on error rather than failing
        return {
            "LI post": "",
            "X post": "",
            "Bsky post": ""
        }


def _assemble_linkedin_post(li_content: str, event_name: str, yt_full_link: str, resources: str) -> str:
    """Assemble LinkedIn post following template"""
    if not li_content:
        return ""
    
    parts = [li_content]
    
    # Add CTA and resources section
    if event_name or yt_full_link or resources:
        parts.append("")  # Empty line
        parts.append(f"Link to {event_name} recording & resources in comments 👇")
        
        if yt_full_link:
            parts.append("")  # Empty line
            parts.append(f"▶️ Full recording: {yt_full_link}")
        
        if resources:
            parts.append("")  # Empty line
            parts.append(f"📄 {resources}")
    
    return "\n".join(parts)


def _assemble_x_post(x_content: str, event_name: str, yt_full_link: str, resources: str) -> str:
    """Assemble X/Twitter post following template"""
    if not x_content:
        return ""
    
    parts = [f"{x_content} 👇"]
    
    # Add video and resources
    if yt_full_link:
        parts.append("")  # Empty line
        parts.append(f"▶️ Watch {event_name} recording: {yt_full_link}")
    
    if resources:
        parts.append("")  # Empty line  
        parts.append(f"📄 {resources}")
    
    return "\n".join(parts)


def _assemble_bsky_post(x_content: str, event_name: str, yt_full_link: str, resources: str) -> str:
    """Assemble Bluesky post (same format as X/Twitter)"""
    # Bluesky uses same format as X/Twitter
    return _assemble_x_post(x_content, event_name, yt_full_link, resources)


def format_resources_for_social(resources: str) -> str:
    """
    Format resources string for social media display
    
    Takes raw resources from crew output and formats for social posts
    """
    if not resources or not resources.strip():
        return ""
    
    # If resources is already formatted with links, return as-is
    if "http" in resources.lower():
        return resources.strip()
    
    # Otherwise return as-is (crew should handle formatting)
    return resources.strip()