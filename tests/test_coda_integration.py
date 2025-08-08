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
        """Provide test Coda identifiers - REPLACE WITH YOUR ACTUAL VALUES"""
        return {
            "doc_id": "your_doc_id_here",  # Replace with actual doc ID
            "table_id": "your_table_id_here",  # Replace with actual table ID  
            "row_id": "your_row_id_here",  # Replace with actual row ID
            "this_row": "your_table_id_here/your_row_id_here"  # table_id/row_id format
        }
    
    def test_read_coda_data(self, coda_tool, test_coda_ids):
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
        expected_columns = ["Speaker", "Title", "Event", "Transcript"]
        
        for col in expected_columns:
            print(f"Column '{col}': {'✓ Present' if col in data else '✗ Missing'}")
        
        print(f"Available columns: {list(data.keys())}")
        print(f"Sample data: {dict(list(data.items())[:3])}")  # First 3 columns
    
    @pytest.mark.asyncio
    async def test_get_coda_data_function(self, test_coda_ids):
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
    
    def test_write_coda_data_single_column(self, coda_tool, test_coda_ids):
        """Test writing a single column to Coda"""
        test_value = f"Test update at {json.loads('{}')}"  # Simple timestamp
        
        updates = [{
            "row_id": test_coda_ids["row_id"],
            "updates": {
                "Progress": f"🧪 Pytest single column test: {test_value}"
            }
        }]
        
        result = coda_tool.update_rows(
            test_coda_ids["doc_id"],
            test_coda_ids["table_id"], 
            updates
        )
        
        # Parse result and verify success
        result_data = json.loads(result)
        print(f"Update result: {result}")
        
        assert result_data["successful_updates"] >= 1
        assert "Successfully" in str(result_data["results"])
    
    def test_write_coda_data_multiple_columns(self, coda_tool, test_coda_ids):
        """Test writing multiple columns to Coda (the main issue we're fixing)"""
        import time
        timestamp = str(int(time.time()))
        
        updates = [{
            "row_id": test_coda_ids["row_id"],
            "updates": {
                "Progress": f"🧪 Pytest multi-column test: {timestamp}",
                "X content": f"Test X content update {timestamp}",
                "Summaries status": "Testing",
                "Hooks (AI)": f"Test hook {timestamp}"
            }
        }]
        
        result = coda_tool.update_rows(
            test_coda_ids["doc_id"],
            test_coda_ids["table_id"],
            updates
        )
        
        # Parse result and check details
        result_data = json.loads(result)
        print(f"Multi-column update result: {result}")
        
        # Verify success
        assert result_data["total_updates_attempted"] == 4
        print(f"Updates attempted: {result_data['total_updates_attempted']}")
        print(f"Successful updates: {result_data['successful_updates']}")
        
        # Check individual results
        for result_line in result_data["results"]:
            print(f"Result: {result_line}")
            
        # The key test: X content should update successfully now
        results_str = str(result_data["results"])
        if "X content" in updates[0]["updates"]:
            # Either X content succeeded, or it failed for a reason other than rate limiting
            assert "429" not in results_str, "Rate limiting still occurring"
            
        # At least some updates should succeed
        assert result_data["successful_updates"] > 0
    
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