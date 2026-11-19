#!/usr/bin/env python3
"""Check that Selenium can start Chrome/Chromium on THIS machine (no website is contacted).

It loads a tiny local data: page, reads it back and prints which browser/driver were used.
Browser/driver discovery is the same as in ia_selenium_scraper.py (arguments, CHROME_BINARY /
CHROMEDRIVER, PATH, then Selenium Manager). Run it before any measurement:

    python scrapers/check_selenium_env.py               # visible window
    python scrapers/check_selenium_env.py --headless
"""
import argparse
import os
import platform
import shutil
import sys
import tempfile
from types import SimpleNamespace

from ia_selenium_scraper import build_driver


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--chrome-binary")
    p.add_argument("--chromedriver")
    p.add_argument("--headless", action="store_true")
    a = p.parse_args()
    print(f"machine={platform.machine()} os={platform.platform()} python={sys.version.split()[0]}")
    print(f"DISPLAY={os.environ.get('DISPLAY')!r}  CHROME_BINARY={os.environ.get('CHROME_BINARY')!r}  "
          f"CHROMEDRIVER={os.environ.get('CHROMEDRIVER')!r}")
    profile = tempfile.mkdtemp(prefix="labnet_chrome_check_")
    args = SimpleNamespace(chrome_binary=a.chrome_binary, chromedriver=a.chromedriver, headless=a.headless,
                           page_load_strategy="normal", page_timeout=30, chrome_arg=[])
    driver = None
    try:
        driver, info = build_driver(args, profile)
        driver.get("data:text/html,<title>selenium ok</title><h1 id='x'>hello</h1>")
        print(f"browser={info['browser_version']} driver={info['driver_version']}")
        print(f"binary={info['chrome_binary']} driver_path={info['chromedriver']}")
        print("page title:", driver.title, "| h1:", driver.find_element("id", "x").text)
        print("RESULT: selenium ok")
        return 0
    except Exception as exc:
        print("RESULT: FAILED -", type(exc).__name__, str(exc).splitlines()[0][:300])
        print("See docs/SETUP_UBUNTU_VM.md (browser/driver setup, ARM notes, CHROME_NO_SANDBOX).")
        return 1
    finally:
        if driver is not None:
            driver.quit()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
