#!/usr/bin/env python3
"""Headless browser check of the docs/ page's mass search against the library's search_mass().

Not collected by pytest (lives in scripts/, needs Playwright). Run from the package dir after
``uv run --extra server python scripts/export_json.py``::

    uv run --with playwright python -m playwright install chromium   # once
    uv run --with playwright python scripts/test_mass_search.py

The same script is used in psimodpy, unimodpy and uniprotptmpy; only CONFIG differs.
"""

from __future__ import annotations

import importlib
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.name
CONFIG = {
    # the entry's ID as the table shows it, and a text query to combine with mass search
    "psimodpy": {"id": lambda e: f"MOD:{e.id:05d}", "text": ("phospho", "acetyl")},
    "unimodpy": {"id": lambda e: f"UNIMOD:{e.id}", "text": ("phospho", "acetyl")},
    "uniprotptmpy": {"id": lambda e: e.id, "text": ("phospho", "acetyl")},
}[PKG]
KNOWN = [42.010565, 79.966331, 15.994915]
QUERIES = [  # (delta, tolerance in Da) cross-checked against search_mass
    (42.010565, 0.01),
    (79.966331, 0.005),
    (15.994915, 0.02),
    (-18.010565, 0.01),
    (14.01565, 0.0),
]

errors: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        errors.append(msg)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    if not (ROOT / "docs" / "data.json").exists():
        sys.exit("docs/data.json missing: run scripts/export_json.py first")
    db = importlib.import_module(PKG).load()
    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "-d", str(ROOT / "docs")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}/index.html"
    try:
        time.sleep(0.5)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            console: list[str] = []
            page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console.append(str(e)))

            def load(query: str = "") -> None:
                page.goto(base + query)
                page.wait_for_function("document.getElementById('ec').textContent.includes('entries')")
                page.wait_for_timeout(50)

            def ids() -> list[str]:
                return page.eval_on_selector_all("#tbody tr.dr td.ic", "els=>els.map(e=>e.textContent.trim())")

            def errs() -> list[str]:
                return page.eval_on_selector_all("#tbody tr.dr td.ec", "els=>els.map(e=>e.textContent.trim())")

            def settle() -> None:
                page.wait_for_timeout(350)  # inputs are debounced by 200 ms

            load()
            page.select_option("#pp", "0")
            n_all = len(ids())
            check(not page.is_visible("th[data-col=_err]"), "error column hidden with no mass")

            # Known mods found, closest first, error column visible.
            for m in KNOWN:
                page.fill("#mdelta", str(m))
                settle()
                got = ids()
                exp = [CONFIG["id"](e) for e, _ in db.search_mass(m, tolerance=0.01)]
                check(len(got) > 0 and page.is_visible("th[data-col=_err]"), f"{m}: found {len(got)} hits")
                check(got == exp, f"{m}: order matches search_mass ({len(exp)} hits)")
                e0 = errs()
                check(bool(e0) and abs(float(e0[0])) <= 0.01, f"{m}: first error {e0[:1]}")
                check("mass=" in page.url and "tol=0.01" in page.url and "unit=da" in page.url, f"{m}: URL {page.url}")

            # Cross-check with Python search_mass, including tolerance 0 and negative deltas.
            for delta, tol in QUERIES:
                load(f"?mass={delta}&tol={tol}&unit=da")
                page.select_option("#pp", "0")
                got = ids()
                exp = [CONFIG["id"](e) for e, _ in db.search_mass(delta, tolerance=tol)]
                check(got == exp, f"cross-check {delta}±{tol}: page {len(got)} vs library {len(exp)}")

            # Tolerance boundaries: put an entry exactly on the edge of the window.
            hit, _ = db.search_mass(79.966331, tolerance=0.001)[0]
            mass = hit.get_mass()
            key = CONFIG["id"](hit)
            for tol, inside in ((0.01, True), (0.00999, False)):
                load(f"?mass={mass + 0.01!r}&tol={tol}&unit=da")
                page.select_option("#pp", "0")
                lib = any(CONFIG["id"](e) == key for e, _ in db.search_mass(mass + 0.01, tolerance=tol))
                check((key in ids()) == inside == lib, f"edge tol={tol}: {key} inside={inside} (library {lib})")

            # ppm: needs a precursor; tol_Da = ppm * precursor / 1e6.
            load("?mass=79.966331&tol=0.01&unit=da")
            page.select_option("#pp", "0")
            page.select_option("#munit", "ppm")
            settle()
            check(page.input_value("#mtol") == "10", "switching to ppm sets default tolerance 10")
            check(page.is_visible("#mprec"), "precursor input shown for ppm")
            check("precursor" in page.text_content("#mmsg"), "ppm without precursor explains itself")
            check(len(ids()) == n_all, "ppm without precursor does not filter")
            page.fill("#mprec", "1000")
            settle()
            exp = [CONFIG["id"](e) for e, _ in db.search_mass(79.966331, tolerance=10 * 1000 / 1e6)]
            check(ids()[: len(exp)] == exp and len(ids()) == len(exp), f"ppm 10 @1000 Da == 0.01 Da ({len(exp)} hits)")
            check(page.text_content("#merrh") == "Δ error (ppm)", "error header says ppm")
            e_ppm = [float(v) for v in errs()]
            check(all(abs(v) <= 10 + 1e-6 for v in e_ppm), f"ppm errors within 10: {e_ppm[:3]}")
            check("unit=ppm" in page.url and "prec=1000" in page.url, f"ppm URL {page.url}")

            # URL round-trip: reload the shared URL, same state and rows.
            url, before = page.url, ids()
            page.goto("about:blank")
            page.goto(url)
            page.wait_for_function("document.getElementById('ec').textContent.includes('entries')")
            page.select_option("#pp", "0")
            check(
                page.input_value("#munit") == "ppm" and page.input_value("#mprec") == "1000", "URL restores ppm state"
            )
            check(ids() == before, "URL round-trip restores rows")

            # Mono / average toggle.
            load("?mass=79.9663&tol=0.01&unit=da&mass_type=avg")
            page.select_option("#pp", "0")
            check(page.input_value("#mtype") == "avg", "mass_type=avg restored")
            load("?mass=79.9799&tol=0.01&unit=da&mass_type=avg")
            page.select_option("#pp", "0")
            exp_avg = {
                CONFIG["id"](e)
                for e in db
                if e.get_mass(monoisotopic=False) is not None
                and abs(79.9799 - e.get_mass(monoisotopic=False)) <= 0.01
                and not getattr(e, "is_obsolete", False)
            }
            check(set(ids()) == exp_avg and len(exp_avg) > 0, f"average mass search ({len(exp_avg)} hits)")

            # Text search combined with mass search, and in the URL.
            load("?mass=79.966331&tol=0.01&unit=da")
            page.select_option("#pp", "0")
            n_mass = len(ids())
            page.fill("#q", CONFIG["text"][0])
            settle()
            both = ids()
            check(0 < len(both) < n_mass, f"text+mass narrows {n_mass} -> {len(both)}")
            check("q=" in page.url and "mass=" in page.url, "URL has q and mass")

            # Sorting by error column toggles; another column click keeps the filter.
            page.click("th[data-col=_err]")
            e_desc = [abs(float(v)) for v in errs()]
            check(e_desc == sorted(e_desc, reverse=True), "error column sorts descending on second click")
            page.click("th[data-col=name]")
            check(len(ids()) == len(both), "sorting by name keeps mass filter")

            # Detail view keeps the list state, back restores it.
            page.click("#tbody tr.dr")
            check("id=" in page.url and "mass=" in page.url, f"detail URL keeps state {page.url}")
            page.click("#dvb")
            check("id=" not in page.url and "mass=" in page.url and len(ids()) == len(both), "back to list keeps state")

            # Clearing the mass restores the full list and hides the column.
            page.fill("#q", "")
            page.fill("#mdelta", "")
            settle()
            check(len(ids()) == n_all and "mass=" not in page.url, "clearing mass restores full list")
            check(not page.is_visible("th[data-col=_err]"), "error column hidden again")

            # Bad input.
            page.fill("#mdelta", "abc")
            settle()
            check("number" in page.text_content("#mmsg") and len(ids()) == n_all, "bad mass reported, no filter")

            # Malformed URLs: no filter, a message, no crash; a dead id is dropped from the URL.
            for query, why in (
                ("?mass=0x2A&tol=0.01&unit=da", "hex mass"),
                ("?mass=Infinity&tol=0.01&unit=da", "Infinity mass"),
                ("?mass=1e400&tol=0.01&unit=da", "overflowing mass"),
                ("?mass=42.0106&tol=-1&unit=da", "negative tolerance"),
                ("?mass=42.0106&tol=abc&unit=da", "text tolerance"),
                ("?mass=42.0106&tol=10&unit=ppm&prec=-5", "negative precursor"),
            ):
                load(query)
                page.select_option("#pp", "0")
                check(
                    len(ids()) == n_all and page.text_content("#mmsg") != "", f"malformed ({why}): no filter, message"
                )
            load("?id=99999999&mass=42.010565&tol=0.01&unit=da")
            check("id=" not in page.url and "mass=" in page.url, f"unknown id dropped from URL: {page.url}")
            check(not page.is_visible("#dvp"), "unknown id shows the list")

            # Unit switch resets the tolerance to that unit's default, both ways.
            load("?mass=42.010565&tol=0.02&unit=da")
            page.select_option("#munit", "ppm")
            check(page.input_value("#mtol") == "10", "Da 0.02 -> ppm resets tolerance to 10")
            page.select_option("#munit", "da")
            check(page.input_value("#mtol") == "0.01", "ppm -> Da resets tolerance to 0.01")

            # Descending error sort keeps ties in library order (mass, then database order).
            load("?mass=42.010565&tol=0.05&unit=da")
            page.select_option("#pp", "0")
            lib = db.search_mass(42.010565, tolerance=0.05)
            groups: dict[float, list[str]] = {}
            for e, err in lib:
                groups.setdefault(round(abs(err), 9), []).append(CONFIG["id"](e))
            exp_desc = [i for k in sorted(groups, reverse=True) for i in groups[k]]
            page.click("th[data-col=_err]")
            check(ids() == exp_desc, f"descending error sort keeps tie order ({len(exp_desc)} rows)")

            # Back/forward: list -> detail -> list with another mass; back twice restores the first state.
            load("?mass=42.010565&tol=0.01&unit=da")
            page.select_option("#pp", "0")
            n42 = len(ids())
            page.click("#tbody tr.dr")
            page.go_back()
            page.wait_for_timeout(200)
            check(not page.is_visible("#dvp") and "mass=42.010565" in page.url, "browser back closes detail")
            page.go_forward()
            page.wait_for_timeout(200)
            check(page.is_visible("#dvp") and "id=" in page.url, "browser forward reopens detail")
            page.click("#dvb")
            page.fill("#mdelta", "79.966331")
            settle()
            page.go_back()
            page.wait_for_timeout(200)
            page.go_back()
            page.wait_for_timeout(300)
            page.select_option("#pp", "0")
            check(
                page.input_value("#mdelta") == "42.010565" and len(ids()) == n42, f"back twice restores 42 ({page.url})"
            )

            check(not console, f"no console errors {console}")
            browser.close()
    finally:
        server.terminate()
        server.wait()
    print(f"\n{len(errors)} failure(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
