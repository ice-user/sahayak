"""Polite collector for myscheme.gov.in (a JS-rendered Next.js app the plain fetcher cannot read).

Two jobs, both done with a headless Chromium (Playwright) that identifies itself and waits at least
``--delay`` seconds (default 2) between actions:

  python scripts/collect_myscheme.py list              # crawl the search listing -> data/sources/myscheme_urls.txt
  python scripts/collect_myscheme.py snapshot URL...   # render scheme pages -> data/sources/myscheme/<slug>.txt
  python scripts/collect_myscheme.py snapshot --from-file data/sources/myscheme_urls.txt --limit 20 --group central

robots.txt of the site allows everything. No API endpoints or keys are called by this script directly; it only
reads what the site's own front end renders. The snapshots are plain text with a header line naming the source
URL, saved under data/ so `python -m research run --file ... --source-url ...` and merge integrity checks work.

Install: pip install playwright && python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "sources"
BASE = "https://www.myscheme.gov.in"
UA = "SahayakResearchBot/0.1 (scheme research pilot; headless, <=1 action per 2s; robots.txt respected)"

_PAGER_UL = "[...document.querySelectorAll('ul')].find(u => u.querySelector('li.bg-green-700'))"


class Throttle:
    def __init__(self, delay: float):
        self.delay, self.last = delay, 0.0

    def wait(self):
        gap = time.monotonic() - self.last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self.last = time.monotonic()


def _browser(p):
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(user_agent=UA, viewport={"width": 1500, "height": 1000}, locale="en-IN")
    return b, ctx.new_page()


def _hrefs(pg) -> list[str]:
    return [h.split("?")[0] for h in pg.eval_on_selector_all(
        "a[href^='/schemes/']", "els => els.map(e => e.getAttribute('href'))")]


def _wait_change(pg, before: list[str], timeout=20.0) -> list[str]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        now = _hrefs(pg)
        if now and now != before:
            return now
        time.sleep(0.4)
    return _hrefs(pg)


def _pager(pg) -> tuple[int, int, bool]:
    """(current page, last page, next arrow enabled)."""
    return pg.evaluate("""() => {
      const ul = %s;
      if (!ul) return [1, 1, false];
      const lis = [...ul.querySelectorAll('li')];
      const cur = lis.find(l => l.className.includes('bg-green-700'));
      const svgs = ul.querySelectorAll(':scope > svg');
      const next = svgs[svgs.length - 1];
      return [cur ? +cur.innerText : 1, +lis[lis.length - 1].innerText,
              !!next && !next.getAttribute('class').includes('not-allowed')];
    }""" % _PAGER_UL)


def _crawl_pages(pg, th: Throttle, label: str, log) -> list[str]:
    out: list[str] = []
    while True:
        cur, last, can_next = _pager(pg)
        hs = _hrefs(pg)
        out += [h for h in hs if h not in out]
        log(f"  {label}: page {cur}/{last} total {len(out)}")
        if not can_next or cur >= last:
            return out
        th.wait()
        pg.evaluate("""() => { const ul = %s;
          const s = ul.querySelectorAll(':scope > svg');
          s[s.length - 1].dispatchEvent(new MouseEvent('click', {bubbles: true})); }""" % _PAGER_UL)
        _wait_change(pg, hs)


def cmd_list(a) -> None:
    from playwright.sync_api import sync_playwright

    ckpt = Path(a.checkpoint)
    done: dict[str, list[str]] = json.loads(ckpt.read_text()) if ckpt.exists() else {}
    th = Throttle(a.delay)

    def log(m):
        print(m, flush=True)

    with sync_playwright() as p:
        b, pg = _browser(p)
        pg.goto(BASE + "/search", wait_until="networkidle", timeout=60000)
        th.wait()
        if "central" not in done:
            pg.get_by_text("Central Schemes", exact=True).first.click()
            time.sleep(3)
            done["central"] = _crawl_pages(pg, th, "central", log)
            ckpt.write_text(json.dumps(done))
        def open_state_select():
            th.wait()
            pg.goto(BASE + "/search", wait_until="networkidle", timeout=60000)
            time.sleep(2)
            pg.get_by_text("State/UT Schemes", exact=True).first.click()
            time.sleep(3)
            # 5th facet = visible State/UT select (the first four are hidden mobile copies)
            pg.locator(".facet__control").nth(4).click()

        open_state_select()
        states = pg.evaluate("[...document.querySelectorAll('[id*=option]')].map(x=>x.innerText)")
        for st in states:
            if st in done:
                continue
            # The select accumulates choices, so every state starts from a freshly loaded page.
            open_state_select()
            before = _hrefs(pg)
            pg.locator("[id*=option]").filter(has_text=st).first.click()
            _wait_change(pg, before)
            time.sleep(1.5)
            done[st] = _crawl_pages(pg, th, st, log)
            ckpt.write_text(json.dumps(done))
        b.close()
    write_url_file(done, Path(a.out))


def write_url_file(done: dict[str, list[str]], out: Path) -> None:
    central = done.get("central", [])
    state_map: dict[str, list[str]] = {}
    for st, hs in done.items():
        if st == "central":
            continue
        for h in hs:
            state_map.setdefault(h, []).append(st)
    cset = set(central)
    state_only = {h: s for h, s in state_map.items() if h not in cset}
    multi = sum(1 for s in state_only.values() if len(s) > 1)
    lines = [f"# myscheme.gov.in scheme URLs, collected {time.strftime('%Y-%m-%d')} by scripts/collect_myscheme.py",
             f"# total {len(cset) + len(state_only)}: central {len(cset)}, state/UT {len(state_only)}"
             f" (state schemes listed under several states: {multi})",
             "# format: URL  # central | state:<State>[,<State>...]"]
    lines += [f"{BASE}{h}  # central" for h in central]
    lines += [f"{BASE}{h}  # state:{','.join(s)}" for h, s in sorted(state_only.items())]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(lines[1])


def snapshot_text(pg) -> str:
    body = pg.inner_text("main") if pg.locator("main").count() else pg.inner_text("body")
    return re.sub(r"[ \t ﻿]+", " ", body).strip()


def cmd_snapshot(a) -> None:
    from playwright.sync_api import sync_playwright

    urls = list(a.urls)
    if a.from_file:
        for ln in Path(a.from_file).read_text(encoding="utf-8").splitlines():
            if ln.strip() and not ln.startswith("#"):
                tag = ln.split("#", 1)[1].strip() if "#" in ln else ""
                if not a.group or tag.startswith(a.group):
                    urls.append(ln.split()[0])
    urls = urls[: a.limit] if a.limit else urls
    out_dir = SRC / "myscheme"
    out_dir.mkdir(parents=True, exist_ok=True)
    th = Throttle(a.delay)
    with sync_playwright() as p:
        b, pg = _browser(p)
        for u in urls:
            slug = u.rstrip("/").rsplit("/", 1)[-1]
            f = out_dir / f"{slug}.txt"
            if f.exists() and not a.force:
                print("have", slug)
                continue
            th.wait()
            try:
                pg.goto(u, wait_until="networkidle", timeout=60000)
                pg.wait_for_selector("text=Eligibility", timeout=20000)
            except Exception as e:  # noqa: BLE001
                print("FAIL", slug, type(e).__name__)
                continue
            f.write_text(f"Source URL: {u}\n\n{snapshot_text(pg)}\n", encoding="utf-8")
            print("saved", slug, f.stat().st_size)
        b.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delay", type=float, default=2.0, help="min seconds between page actions (>=2)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("list")
    l.add_argument("--out", default=str(SRC / "myscheme_urls.txt"))
    l.add_argument("--checkpoint", default=str(SRC / ".myscheme_listing_checkpoint.json"))
    s = sub.add_parser("snapshot")
    s.add_argument("urls", nargs="*")
    s.add_argument("--from-file")
    s.add_argument("--group", help="central | state")
    s.add_argument("--limit", type=int)
    s.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.delay < 2:
        sys.exit("refusing --delay below 2 seconds")
    {"list": cmd_list, "snapshot": cmd_snapshot}[a.cmd](a)


if __name__ == "__main__":
    main()
