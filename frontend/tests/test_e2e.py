# frontend/tests/test_e2e.py

import pytest
from playwright.sync_api import Page


@pytest.mark.usefixtures("anyio_backend")
def test_add_edit_delete_position(page: Page):
    # 1) Open the dashboard
    page.goto("http://localhost:8501")
    page.wait_for_selector("text=➕ Add Position", timeout=30000)

    # 2) Add a new position
    page.click("text=➕ Add Position")
    page.wait_for_selector("input[aria-label='Ticker Symbol']", timeout=10000)
    page.fill("input[aria-label='Ticker Symbol']", "E2E")
    page.fill("input[aria-label='Quantity']", "1")
    page.fill("input[aria-label='Cost Price']", "100")
    page.click("button:has-text('Add')")

    # Wait for the success banner to be attached to the DOM
    page.wait_for_selector("p:has-text('Added E2E')", state="attached", timeout=10000)

    # And ensure the row actually shows up in the table
    assert page.is_visible("td:has-text('E2E')")

    # 3) Edit that position’s quantity from 1 → 2
    page.click("button:has-text('✏️')", timeout=10000)
    page.wait_for_selector("input[aria-label='Quantity']", timeout=10000)
    page.fill("input[aria-label='Quantity']", "2")
    page.click("button:has-text('Save')")
    page.wait_for_selector("p:has-text('Updated E2E')", state="attached", timeout=10000)

    # Check that the table cell updated
    qty_cell = page.locator("tr:has-text('E2E') >> td:nth-child(2)")
    assert qty_cell.inner_text().startswith("2")

    # 4) Delete the position
    page.click("button:has-text('🗑️')", timeout=10000)
    # Confirm Streamlit's confirm dialog
    page.click("button:has-text('Yes')", timeout=5000)
    page.wait_for_selector("p:has-text('Deleted E2E')", state="attached", timeout=10000)

    # Finally, ensure it's gone
    assert page.locator("tr:has-text('E2E')").count() == 0
