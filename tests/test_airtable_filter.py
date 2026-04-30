"""Test that get_campaigning_leads uses a filtered Airtable formula."""
from unittest.mock import patch, MagicMock


def test_get_campaigning_leads_uses_formula():
    from app import airtable_client

    mock_table = MagicMock()
    mock_table.all.return_value = [
        {"id": "rec1", "fields": {"Address": "123 Main St", "Status": "Campaigning"}},
    ]
    with patch.object(airtable_client, "_get_table", return_value=mock_table):
        result = airtable_client.get_campaigning_leads()
        mock_table.all.assert_called_once_with(formula="{Status} = 'Campaigning'")
        assert len(result) == 1
