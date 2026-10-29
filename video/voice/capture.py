import time
from playwright.sync_api import sync_playwright

T0 = time.time()
def log(*a): print(f"[{time.time()-T0:6.1f}]", *a, flush=True)

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    pg.goto("https://model-x-ray.vercel.app/", wait_until="networkidle")
    start = time.time()
    def at(ms):
        left = ms / 1000 - (time.time() - start)
        if left > 0: time.sleep(left)
    at(3400); pg.screenshot(path="cap/01-landing-error.png"); log("landing error")
    at(8000); pg.screenshot(path="cap/02-landing-fixed.png"); log("landing fixed")
    for i, anchor in enumerate(["Did you know that?", "Our answer", "How it works", "Strengths", "Stack"]):
        pg.get_by_role("link", name=anchor).first.click()
        time.sleep(4.8)
        pg.screenshot(path=f"cap/03-section-{i}.png"); log("section", anchor)
    pg.evaluate("window.scrollTo(0,0)"); time.sleep(1)
    pg.get_by_role("button", name="Try the demo →").first.click()
    seen = set()
    while True:
        text = pg.inner_text("main")
        prog = next((l for l in text.splitlines() if l.startswith("PROGRESS")), "?")
        status = next((l for l in text.splitlines() if l in ("Checking the model", "1 error detected", "No errors found", "Review complete", "Interrupted")), "?")
        key = prog + status
        if key not in seen:
            seen.add(key); n = len(seen)
            pg.screenshot(path=f"cap/10-run-{n}.png"); log("run", prog, status)
        if status != "Checking the model" or time.time() - T0 > 400: break
        time.sleep(1.5)
    time.sleep(1.5); pg.screenshot(path="cap/11-error-found.png")
    pg.locator(".erow").first.click(); time.sleep(1.2)
    pg.screenshot(path="cap/12-error-open.png"); pg.screenshot(path="cap/12-error-open-full.png", full_page=True); log("opened")
    pg.get_by_role("button", name="Open in the sheet").first.click(); time.sleep(2.5)
    pg.screenshot(path="cap/13-sheet.png"); log("sheet")
    pg.keyboard.press("Escape"); time.sleep(1)
    ask = pg.get_by_placeholder("Ask the agent about the error or the fix")
    ask.scroll_into_view_if_needed(); ask.click(); ask.type("Could this value be deliberate?", delay=40)
    pg.screenshot(path="cap/14-ask-typed.png")
    pg.get_by_role("button", name="Ask", exact=True).click(); time.sleep(1)
    pg.screenshot(path="cap/15-ask-thinking.png")
    for _ in range(60):
        if "Thinking…" not in pg.inner_text("main"): break
        time.sleep(1)
    time.sleep(0.8); pg.screenshot(path="cap/16-ask-answer.png"); log("answer")
    approve = pg.get_by_role("button", name="Approve fix")
    approve.scroll_into_view_if_needed(); time.sleep(0.5)
    pg.screenshot(path="cap/17-before-approve.png")
    approve.click(); time.sleep(0.8); pg.screenshot(path="cap/18-approving.png"); log("approving")
    seen = set(); t = time.time()
    while time.time() - t < 300:
        text = pg.inner_text("main")
        lines = [l for l in text.splitlines() if l.strip()]
        key = " | ".join(lines[:12])
        if key not in seen:
            seen.add(key); n = len(seen)
            pg.evaluate("window.scrollTo(0,0)")
            pg.screenshot(path=f"cap/20-after-{n:02d}.png"); log("after", lines[5:9])
        if "Review complete" in lines[:12] or "No errors found" in lines[:12] or ("1 error detected" in lines[:12] and n > 2):
            break
        time.sleep(2)
    pg.screenshot(path="cap/21-final.png"); pg.screenshot(path="cap/21-final-full.png", full_page=True)
    print(pg.inner_text("main")[:1500])
    b.close()
