# Setup on an Ubuntu virtual machine (for Issa's measurements)

The scrapers contain **no hard-coded browser or driver paths**. They are found through arguments, environment
variables, `PATH`, or Selenium Manager (in that order). Tested here: Ubuntu 26.04 on WSL2, x86-64, Python 3.14,
`selenium` 4.52, Chrome for Testing 157. Everything else below (ARM VM, snap/apt Chromium, other Python versions)
is **untested by me**; use the check script to find out quickly.

## 1. Which CPU does the VM have?
```bash
uname -m        # x86_64  -> Intel Mac / x86 VM      aarch64 -> Apple-silicon Mac VM
```

## 2. Packages and Python environment
```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip tcpdump tshark iftop nload ufw
git clone https://github.com/Mhmd-Shkeir/Lab-Network-Project.git
cd Lab-Network-Project
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # requests, beautifulsoup4, selenium (scrapers only)
```
Wireshark GUI (for screenshots): `sudo apt install -y wireshark` and let your user capture:
`sudo usermod -aG wireshark $USER` (log out/in). `tcpdump` needs `sudo`.
Analysis packages (pandas, scikit-learn, …) are in `requirements-analysis.txt` and are not needed for scraping.

## 3. Browser and driver for Selenium

Chrome/Chromium **and** chromedriver must have the same major version.

**x86-64 (Intel Mac VM or x86 Linux)** – easiest: do nothing. On the first run Selenium Manager downloads a matching
Chrome for Testing and driver (needs internet, ~150 MB; I could not test this path because the download kept timing out on my
slow connection, so I used a manually downloaded Chrome for Testing through `CHROME_BINARY`/`CHROMEDRIVER`). Alternatively install Google Chrome
(`https://www.google.com/chrome/`, `.deb`) and Selenium Manager will fetch only the driver.

**aarch64 (Apple-silicon MacBook running an ARM Ubuntu VM)** – Google Chrome and Chrome for Testing have **no Linux ARM build**,
so Selenium Manager cannot supply a browser. You need a Chromium **and** a matching chromedriver built for ARM. Options (not tested by me):
1. Ubuntu snap: `sudo snap install chromium`, then
   `export CHROME_BINARY=/snap/bin/chromium` and `export CHROMEDRIVER=/snap/bin/chromium.chromedriver`
   (snap confinement sometimes blocks the temp profile folder; if it does, try option 2).
2. A distribution package that ships both for ARM (for example Debian's `chromium` + `chromium-driver`, using that distribution's supported packages).
   Then `which chromium chromedriver` should print both; no variables needed.
3. If neither works, tell Mohammad: all three measured methods should run on one working Linux environment, such as his x86-64 WSL machine. Do not combine per-method timings from different machines.

Set once per terminal (or put in `~/.bashrc`):
```bash
export CHROME_BINARY=/path/to/chrome-or-chromium      # optional if found on PATH
export CHROMEDRIVER=/path/to/chromedriver             # optional if found on PATH
export CHROME_NO_SANDBOX=1                             # only if Chrome refuses to start as root / in the VM
```

## 4. Check it (does not contact any website)
```bash
python scrapers/check_selenium_env.py                 # visible window (needs the VM desktop)
python scrapers/check_selenium_env.py --headless      # no window
```
Expected last line: `RESULT: selenium ok`. A visible browser needs a desktop session in the VM; `--headless` works without one
(but then say in the report which mode was measured).

## 5. Other settings (environment variables, all optional)

| Variable | Default | Use |
|---|---|---|
| `LABNET_DELAY` | `3.0` | seconds between the end of one request and the start of the next (same as `--delay`) |
| `LABNET_CONTACT` | – | contact text appended to the User-Agent (not committed) |
| `LABNET_USER_AGENT` | project string | replace the whole User-Agent |
| `LABNET_MAX_RETRIES` | `4` | retries after the first attempt (use `1` or `0` for firewall tests) |
| `LABNET_CONNECT_TIMEOUT` / `LABNET_READ_TIMEOUT` | `15` / `45` | seconds (shorten for firewall tests) |
| `LABNET_API_BATCH` | `50` | ids per API call pair |

Python 3.9+ is expected to work (only 3.14 was tested).
