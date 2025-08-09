#!/usr/bin/env python

from src.far_comms.utils.slide_extractor import extract_slide_content
from src.far_comms.utils.coda_client import CodaClient

def update_coda_with_slides():
    """Extract slide content and update Coda row"""
    
    # File and Coda details
    slide_file = '/Users/cheng2/Desktop/agents/far_comms/data/slides/11_50_Xiaoyuan Yi-ValueCompass_updated.pptx.pdf'
    doc_id = 'Jv4r8SGAJp'
    table_id = 'grid-LcVoQIcUB2'
    row_id = 'i-5ITrA0eBC5'
    
    print("🔍 Extracting slide content...")
    
    # Extract slide content
    result = extract_slide_content(slide_file)
    
    if not result.get('success'):
        print(f"❌ Error extracting slides: {result.get('error')}")
        return
    
    slide_content = result.get('content', '')
    print(f"✅ Extracted {len(slide_content)} characters from {result.get('page_count')} pages")
    
    # Update Coda
    print("📊 Updating Coda...")
    coda_client = CodaClient()
    
    column_updates = {
        "Slides": slide_content
    }
    
    update_result = coda_client.update_row(doc_id, table_id, row_id, column_updates)
    print(f"📝 Coda update result: {update_result}")

if __name__ == "__main__":
    update_coda_with_slides()