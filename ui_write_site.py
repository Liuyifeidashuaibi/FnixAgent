from playwright.sync_api import sync_playwright
import time, re

URL = "http://127.0.0.1:5175"
PROMPT = ("请创建一个可直接双击在浏览器打开的个人作品集单页网站，文件名 index.html，"
          "包含「自我介绍 / 项目作品 / 联系方式」三个板块，使用现代渐变风格、纯内联 CSS、"
          "单文件、响应式。只生成这一个文件，不要生成其他文件。")

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True,
                              args=["--no-sandbox", "--disable-dev-shm-usage"])
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(URL, wait_until="networkidle", timeout=30000)
        time.sleep(3)
        # click "新任务" to ensure fresh session (first match)
        try:
            pg.get_by_text("新任务", exact=True).first.click(timeout=5000)
            time.sleep(2)
        except Exception as e:
            print("new-task click skipped:", e)
        # fill composer
        box = pg.get_by_placeholder("描述要构建或交付的内容…")
        box.click()
        box.fill(PROMPT)
        time.sleep(1)
        pg.screenshot(path="E:/FNIX/FnixAgent/ui_2_filled.png")
        # submit
        pg.keyboard.press("Enter")
        print("SUBMITTED")
        time.sleep(6)
        pg.screenshot(path="E:/FNIX/FnixAgent/ui_3_after_submit.png")
        # poll progress
        for i in range(16):
            time.sleep(9)
            txt = pg.inner_text("body")
            snap = re.sub(r"\s+", " ", txt)[:900]
            print(f"--- poll {i} --- {snap}")
            pg.screenshot(path=f"E:/FNIX/FnixAgent/ui_poll_{i}.png")
            low = txt.lower()
            if "违规" in txt or "拦截" in txt or "失败" in txt or "error" in low:
                print(">>> possible error/block detected")
            if "index.html" in txt:
                print(">>> index.html mentioned in UI")
        print("=== CONSOLE ERRORS ===")
        for e in errors[:20]:
            print("ERR:", e[:200])
        b.close()

if __name__ == "__main__":
    main()
