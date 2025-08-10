import pytest
import json
from far_comms.tools.coda_tool import CodaTool, CodaIds
from far_comms.main import get_coda_data
import asyncio

class TestCodaIntegration:
    """Test full Coda read/write integration"""
    
    @pytest.fixture
    def coda_tool(self):
        """Create CodaTool instance for testing"""
        return CodaTool()
    
    @pytest.fixture
    def test_coda_ids(self):
        """Provide test Coda identifiers using CodaIds model"""
        from far_comms.tools.coda_tool import CodaIds
        
        # Update these values as needed for testing
        doc_id = "Jv4r8SGAJp"  # Your Coda document ID
        this_row = "grid-LcVoQIcUB2/i-AbYMTOZsbA"  # this_row format from webhook
        
        return CodaIds.from_this_row(doc_id, this_row)
    
    def test_get_row(self, coda_tool, test_coda_ids):
        """Test reading data from Coda using get_row"""
        # Test the low-level get_row method
        result = coda_tool.get_row(
            test_coda_ids["doc_id"], 
            test_coda_ids["table_id"], 
            test_coda_ids["row_id"]
        )
        
        # Verify we got valid JSON back
        parsed_result = json.loads(result)
        assert "data" in parsed_result
        
        # Check for expected columns (adjust based on your table structure)
        data = parsed_result["data"]
        expected_columns = ["Speaker", "Title", "Event", "YT full link"]
        
        for col in expected_columns:
            print(f"Column '{col}': {'✓ Present' if col in data else '✗ Missing'}")
        
        print(f"Available columns: {list(data.keys())}")
        print(f"Sample data: {dict(list(data.items())[:3])}")  # First 3 columns
    
    @pytest.mark.asyncio
    async def test_get_coda_data(self, test_coda_ids):
        """Test the main.py get_coda_data function"""
        coda_ids, talk_request = await get_coda_data(
            test_coda_ids["this_row"],
            test_coda_ids["doc_id"]
        )
        
        # Verify CodaIds object
        assert coda_ids.doc_id == test_coda_ids["doc_id"]
        assert coda_ids.table_id == test_coda_ids["table_id"] 
        assert coda_ids.row_id == test_coda_ids["row_id"]
        
        # Verify TalkRequest object
        assert talk_request.speaker != ""
        assert talk_request.title != ""
        
        print(f"✓ CodaIds: {coda_ids}")
        print(f"✓ TalkRequest: {talk_request.speaker} - {talk_request.title}")
    
    def test_update_row(self, coda_tool, test_coda_ids):
        """Test writing multiple columns to Coda using update_row directly"""
        import time
        timestamp = str(int(time.time()))
        
        # Test direct update_row method (single API call for multiple columns)
        column_updates = {
            "Webhook progress": f"🧪 Direct update_row test: {timestamp}",
            "X content": f"Test X content {timestamp}",
            "Webhook status": "Testing"
        }
        
        result = coda_tool.update_row(
            test_coda_ids.doc_id,
            test_coda_ids.table_id, 
            test_coda_ids.row_id,
            column_updates
        )
        
        # Check the result (update_row returns a string, not JSON)
        print(f"Update result: {result}")
        
        # Verify success - update_row returns a success message string
        assert "Successfully updated" in result
        assert "Webhook progress" in result
        assert "X content" in result
        assert "Webhook status" in result
        
        # Verify no rate limiting errors
        assert "429" not in result, "Rate limiting occurred"
        assert "Error" not in result, f"Update failed: {result}"
    
    def test_column_discovery(self, coda_tool, test_coda_ids):
        """Test discovering available columns in the table"""
        columns_result = coda_tool.get_columns(
            test_coda_ids["doc_id"],
            test_coda_ids["table_id"]
        )
        
        columns_data = json.loads(columns_result)
        columns = columns_data["columns"]
        
        print(f"Available columns in table:")
        for col_id, col_name in columns.items():
            print(f"  {col_name} (ID: {col_id})")
        
        # Check if our target columns exist
        column_names = list(columns.values())
        target_columns = ["X content", "Progress", "Hooks (AI)", "LI content"]
        
        for target in target_columns:
            status = "✓ Found" if target in column_names else "✗ Missing"
            print(f"{target}: {status}")
            
        # Verify we have the essential columns
        assert "Progress" in column_names, "Progress column missing"
    
    def test_x_handle_lookup(self, coda_tool):
        """Test X handle lookup functionality"""
        # Test with a known speaker name
        x_handle = coda_tool.get_x_handle("Tianwei Zhang")
        print(f"X handle for 'Tianwei Zhang': '{x_handle}'")
        
        # Test with empty/None input
        empty_handle = coda_tool.get_x_handle("")
        assert empty_handle == ""
        print(f"Empty input test: '{empty_handle}'")
        
        # Test with non-existent speaker (should fallback to speaker name)
        fallback_handle = coda_tool.get_x_handle("NonExistent Speaker")
        print(f"Fallback test for 'NonExistent Speaker': '{fallback_handle}'")
        
        # The function should always return a string (never None)
        assert isinstance(x_handle, str)
        assert isinstance(fallback_handle, str)


# Instructions for running the test:
"""
To run this test:

1. First, update the test_coda_ids fixture with your actual values:
   - doc_id: Your Coda document ID
   - table_id: Your table ID (from the this_row parameter)  
   - row_id: A test row ID (from the this_row parameter)

2. Install pytest if needed:
   pip install pytest pytest-asyncio

3. Run the tests:
   cd /Users/cheng2/Desktop/agents/far_comms
   PYTHONPATH=src pytest tests/test_coda_integration.py -v

4. Run specific tests:
   pytest tests/test_coda_integration.py::TestCodaIntegration::test_write_coda_data_multiple_columns -v

The test will show you exactly what's happening with each column update.
"""