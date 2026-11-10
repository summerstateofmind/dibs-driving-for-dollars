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


def _formula_for(fragment):
    from app import airtable_client

    mock_table = MagicMock()
    mock_table.all.return_value = []
    with patch.object(airtable_client, "_get_table", return_value=mock_table):
        airtable_client.find_leads_by_address(fragment)
    return mock_table.all.call_args.kwargs["formula"]


def test_find_leads_escapes_double_quote():
    assert _formula_for('12 "Oak" St') == 'FIND(LOWER("12 \\"Oak\\" St"), LOWER({Address}))'


def test_find_leads_escapes_backslash_before_quote():
    # Input is: x\"), 1=1, ("   -- a backslash followed by a quote must not
    # leave the quote unescaped and close the string early.
    formula = _formula_for('x\\"), 1=1, ("')
    assert formula == 'FIND(LOWER("x\\\\\\"), 1=1, (\\""), LOWER({Address}))'


def test_find_leads_escapes_trailing_backslash():
    assert _formula_for("Main\\") == 'FIND(LOWER("Main\\\\"), LOWER({Address}))'


def test_find_leads_plain_fragment_unchanged():
    assert _formula_for("1234 Main") == 'FIND(LOWER("1234 Main"), LOWER({Address}))'
