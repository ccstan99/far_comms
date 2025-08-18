#!/usr/bin/env python

import logging
from typing import Dict, Optional
from pathlib import Path
from far_comms.utils.coda_client import CodaClient

logger = logging.getLogger(__name__)


def _load_social_templates() -> Dict[str, str]:
    """
    Load social media templates from assemble_socials.md
    
    Returns:
        dict: {"linkedin": template, "x": template, "bsky": template}
    """
    try:
        # Load template file
        # Path: social_assembler.py -> utils -> far_comms -> src -> project_root -> docs
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        template_path = docs_dir / "assemble_socials.md"
        
        if not template_path.exists():
            logger.warning(f"Template file not found: {template_path}")
            return {}
        
        template_content = template_path.read_text()
        
        # Parse template sections
        templates = {}
        
        # Extract LinkedIn template
        linkedin_match = template_content.split('<LINKEDIN POST>')[1].split('</LINKEDIN POST>')[0].strip()
        templates['linkedin'] = linkedin_match
        
        # Extract X template  
        x_match = template_content.split('<X POST>')[1].split('</X POST>')[0].strip()
        templates['x'] = x_match
        
        # Extract Bluesky template
        bsky_match = template_content.split('<BSKY POST>')[1].split('</BSKY POST>')[0].strip()
        templates['bsky'] = bsky_match
        
        logger.info("Successfully loaded social media templates from assemble_socials.md")
        return templates
        
    except Exception as e:
        logger.warning(f"Failed to load social templates: {e}")
        return {}


def assemble_socials(crew_output: dict, coda_data: dict) -> dict:
    """
    Assemble platform-specific social media posts from crew output and Coda data
    
    Args:
        crew_output: Parsed output from promote_talk crew (contains li_content, x_content, resources)
        coda_data: Input data from Coda (contains event_name, yt_full_link, speaker, etc.)
    
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
        speaker_name = coda_data.get("speaker", "").strip()
        
        logger.info(f"Assembling socials - Speaker: {speaker_name}, Event: {event_name}, Resources: {bool(resources)}, Video: {bool(yt_full_link)}")
        
        # Lookup speaker handles using CodaClient
        speaker_handles = _lookup_speaker_handles(speaker_name) if speaker_name else {}
        
        # Assemble LinkedIn post
        li_post = _assemble_linkedin_post(li_content, event_name, yt_full_link, resources, speaker_name, speaker_handles)
        
        # Assemble X/Twitter post  
        x_post = _assemble_x_post(x_content, event_name, yt_full_link, resources, speaker_name, speaker_handles)
        
        # Assemble Bluesky post (same format as X)
        bsky_post = _assemble_bsky_post(x_content, event_name, yt_full_link, resources, speaker_name, speaker_handles)
        
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


def _lookup_speaker_handles(speaker_name: str) -> dict:
    """
    Look up speaker's social media handles using CodaClient
    
    Returns:
        dict: {"x_handle": str, "linkedin_profile": str, "bsky_handle": str}
    """
    try:
        coda_client = CodaClient()
        
        handles = {
            "x_handle": coda_client.get_x_handle(speaker_name),
            "linkedin_profile": coda_client.get_linkedin_profile(speaker_name),
            "bsky_handle": coda_client.get_bsky_handle(speaker_name)
        }
        
        logger.debug(f"Found handles for {speaker_name}: {handles}")
        return handles
        
    except Exception as e:
        logger.warning(f"Failed to lookup handles for {speaker_name}: {e}")
        return {"x_handle": "", "linkedin_profile": "", "bsky_handle": ""}


def _format_speaker_name(speaker_name: str, handle: str, platform: str) -> str:
    """
    Format speaker name with handle according to platform requirements:
    - LinkedIn: @{speaker_name}[{linkedin_profile}]
    - X: @{x_handle}  
    - Bluesky: @{bsky_handle}
    """
    if not handle or not handle.strip():
        return speaker_name  # Fallback to plain name
    
    handle = handle.strip()
    
    if platform == "linkedin":
        # LinkedIn format: @{speaker_name}[{linkedin_profile}]
        return f"@{speaker_name}[{handle}]"
    elif platform in ["x", "bsky"]:
        # X and Bluesky format: @{handle}
        # Ensure handle starts with @
        if not handle.startswith("@"):
            handle = f"@{handle}"
        return handle
    else:
        return speaker_name  # Unknown platform, fallback


def _assemble_linkedin_post(li_content: str, event_name: str, yt_full_link: str, resources: str, speaker_name: str = "", speaker_handles: dict = None) -> str:
    """Assemble LinkedIn post using template or fallback to hardcoded format"""
    if not li_content:
        return ""
    
    # Load templates
    templates = _load_social_templates()
    
    if templates and 'linkedin' in templates:
        # Use template-based formatting
        # Format speaker name with LinkedIn profile if available
        formatted_content = li_content
        if speaker_name and speaker_handles:
            linkedin_profile = speaker_handles.get("linkedin_profile", "")
            formatted_speaker = _format_speaker_name(speaker_name, linkedin_profile, "linkedin")
            # Replace speaker name mentions with formatted version
            formatted_content = formatted_content.replace(speaker_name, formatted_speaker)
        
        # Apply template with variable substitution
        template = templates['linkedin']
        result = template.replace('{li_content}', formatted_content)
        result = result.replace('{event_name}', event_name)
        result = result.replace('{yt_full_url}', yt_full_link)  # Note: template uses yt_full_url, function uses yt_full_link
        result = result.replace('{resources}', resources)
        
        return result
    else:
        # Fallback to hardcoded format
        # Format speaker name with LinkedIn profile if available
        formatted_content = li_content
        if speaker_name and speaker_handles:
            linkedin_profile = speaker_handles.get("linkedin_profile", "")
            formatted_speaker = _format_speaker_name(speaker_name, linkedin_profile, "linkedin")
            # Replace speaker name mentions with formatted version
            formatted_content = formatted_content.replace(speaker_name, formatted_speaker)
        
        parts = [formatted_content]
        
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


def _assemble_x_post(x_content: str, event_name: str, yt_full_link: str, resources: str, speaker_name: str = "", speaker_handles: dict = None) -> str:
    """Assemble X/Twitter post using template or fallback to hardcoded format"""
    if not x_content:
        return ""
    
    # Load templates
    templates = _load_social_templates()
    
    if templates and 'x' in templates:
        # Use template-based formatting
        # Format speaker name with X handle if available
        formatted_content = x_content
        if speaker_name and speaker_handles:
            x_handle = speaker_handles.get("x_handle", "")
            formatted_speaker = _format_speaker_name(speaker_name, x_handle, "x")
            # Replace speaker name mentions with formatted version
            formatted_content = formatted_content.replace(speaker_name, formatted_speaker)
        
        # Apply template with variable substitution
        template = templates['x']
        result = template.replace('{x_content}', formatted_content)
        result = result.replace('{event_name}', event_name)
        result = result.replace('{yt_full_url}', yt_full_link)  # Note: template uses yt_full_url, function uses yt_full_link
        result = result.replace('{resources}', resources)
        
        return result
    else:
        # Fallback to hardcoded format
        # Format speaker name with X handle if available
        formatted_content = x_content
        if speaker_name and speaker_handles:
            x_handle = speaker_handles.get("x_handle", "")
            formatted_speaker = _format_speaker_name(speaker_name, x_handle, "x")
            # Replace speaker name mentions with formatted version
            formatted_content = formatted_content.replace(speaker_name, formatted_speaker)
        
        parts = [f"{formatted_content} 👇"]
        
        # Add video and resources
        if yt_full_link:
            parts.append("")  # Empty line
            parts.append(f"▶️ Watch {event_name} recording: {yt_full_link}")
        
        if resources:
            parts.append("")  # Empty line  
            parts.append(f"📄 {resources}")
        
        return "\n".join(parts)


def _assemble_bsky_post(x_content: str, event_name: str, yt_full_link: str, resources: str, speaker_name: str = "", speaker_handles: dict = None) -> str:
    """Assemble Bluesky post using template or fallback to hardcoded format"""
    if not x_content:
        return ""
    
    # Load templates
    templates = _load_social_templates()
    
    if templates and 'bsky' in templates:
        # Use template-based formatting
        # Format speaker name with Bluesky handle if available (currently not available, so will fall back to speaker name)
        formatted_content = x_content
        if speaker_name and speaker_handles:
            bsky_handle = speaker_handles.get("bsky_handle", "")
            formatted_speaker = _format_speaker_name(speaker_name, bsky_handle, "bsky")
            # Replace speaker name mentions with formatted version
            formatted_content = formatted_content.replace(speaker_name, formatted_speaker)
        
        # Apply template with variable substitution
        template = templates['bsky']
        result = template.replace('{x_content}', formatted_content)
        result = result.replace('{event_name}', event_name)
        result = result.replace('{yt_full_url}', yt_full_link)  # Note: template uses yt_full_url, function uses yt_full_link
        result = result.replace('{resources}', resources)
        
        return result
    else:
        # Fallback to hardcoded format
        # Format speaker name with Bluesky handle if available (currently not available, so will fall back to speaker name)
        formatted_content = x_content
        if speaker_name and speaker_handles:
            bsky_handle = speaker_handles.get("bsky_handle", "")
            formatted_speaker = _format_speaker_name(speaker_name, bsky_handle, "bsky")
            # Replace speaker name mentions with formatted version
            formatted_content = formatted_content.replace(speaker_name, formatted_speaker)
        
        parts = [f"{formatted_content} 👇"]
        
        # Add video and resources
        if yt_full_link:
            parts.append("")  # Empty line
            parts.append(f"▶️ Watch {event_name} recording: {yt_full_link}")
        
        if resources:
            parts.append("")  # Empty line  
            parts.append(f"📄 {resources}")
        
        return "\n".join(parts)


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