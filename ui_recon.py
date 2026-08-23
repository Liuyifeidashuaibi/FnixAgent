from playwright.sync_api import sync_playwright
import time

URL = "http://127.0.0.1:5175"
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True,
                          args=["--no-sandbox", "--disable-dev-shm-usage"])
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.goto(URL, wait_until="networkidle", timeout=30000)
    time.sleep(4)
    pg.screenshot(path="E:/FNIX/FnixAgent/ui_1_initial.png")
    print("TITLE:", pg.title())
    print("URL:", pg.url)
    print("=== BUTTONS ===")
    for el in pg.query_selector_all("button"):
        t = (el.inner_text() or "").strip().replace("\n", " ")
        if t:
            print("BTN:", t[:70])
    print("=== INPUTS/TEXTAREAS ===")
    for el in pg.query_selector_all("input,textarea"):
        ph = el.get_attribute("placeholder") or ""
        nm = el.get_attribute("name") or ""
        tp = el.get_attribute("type") or ""
        print(f"INPUT type={tp} name={nm!r} placeholder={ph!r}")
    print("=== BODY TEXT (first 1800) ===")
    print(pg.inner_text("body")[:1800])
    b.close()
