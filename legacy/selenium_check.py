"""Check that Selenium can launch headless Chrome and read a local test page (no internet scraping)."""
import os
import pathlib
import tempfile
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

page = pathlib.Path(tempfile.mkdtemp()) / "test.html"
page.write_text("<html><body><h1 id='t'>selenium ok</h1><p class='q'>one</p><p class='q'>two</p></body></html>")

CFT = pathlib.Path.home() / "chrome_for_testing"
chrome = os.environ.get("CHROME_BINARY", str(CFT / "chrome-linux64" / "chrome"))
driver_path = os.environ.get("CHROMEDRIVER_PATH", str(CFT / "chromedriver-linux64" / "chromedriver"))

options = webdriver.ChromeOptions()
options.binary_location = chrome
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

start = time.perf_counter()
driver = webdriver.Chrome(service=Service(driver_path), options=options)  # local Chrome for Testing, no download
try:
    driver.get(page.as_uri())
    print("browser:", driver.capabilities["browserName"], driver.capabilities["browserVersion"])
    print("h1:", driver.find_element(By.ID, "t").text)
    print("paragraphs:", [e.text for e in driver.find_elements(By.CLASS_NAME, "q")])
finally:
    driver.quit()
print(f"OK in {time.perf_counter() - start:.1f}s")
