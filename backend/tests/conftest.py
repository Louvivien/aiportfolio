import subprocess
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent  # project root


@pytest.fixture(scope="session", autouse=True)
def streamlit_server():
    # 1) start your Streamlit app in a subprocess
    cmd = [
        "streamlit",
        "run",
        str(ROOT / "frontend" / "app.py"),
        "--server.port",
        "8501",
    ]
    proc = subprocess.Popen(
        cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    time.sleep(5)  # give it time to spin up
    yield
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="session")
def playwright():
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright):
    browser = playwright.chromium.launch()
    yield browser
    browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()
