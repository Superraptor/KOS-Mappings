#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test driver that iterates over the URLs listed in ``test_urls.txt`` and tries
to create SSSOM files from each of them by invoking the ``src/write_sssom_file.py``
script **non‑interactively**.

Key fixes compared with the previous version:

1. **Correct CLI invocation** – the script now supplies the required
   ``-o <outfile>`` argument, so ``write_sssom_file.py`` no longer crashes
   with a ``TypeError``.
2. **Persistent JSON report** – the temporary output directory is **kept**
   after the run (so you can inspect the generated files).  If you really
   want it removed automatically, pass ``--clean‑up``.
3. **Working‑directory fix** – the subprocess now runs with ``cwd=src_dir``,
   which means any *relative* call inside ``write_sssom_file.py`` (e.g.
   ``python generate_sssom_metadata.py``) will correctly resolve to
   ``../src/generate_sssom_metadata.py``.
4. A tiny amount of extra logging to make debugging easier.

Usage
-----
    python -m test.run_urls_test          # from repository root
    # or
    python test/run_urls_test.py [options]

Options
-------
    -v, --verbose          Show DEBUG‑level logging.
    --clean-up             Delete the temporary directory after the run.
    --keep-temp            Alias for the default behaviour (keeps the temp dir).
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict

if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------


def _load_urls(file_path: Path) -> List[str]:
    """Read ``test_urls.txt`` and return a list of URLs (skip blanks/comments)."""
    urls: List[str] = []
    with file_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    return urls


def _run_write_sssom(
    src_dir: Path,
    url: str,
    out_dir: Path,
) -> Dict[str, str]:
    """
    Execute ``src/write_sssom_file.py`` for *one* URL.

    Returns a small dict that will be stored in the final JSON report.
    """
    script_path = src_dir / "write_sssom_file.py"

    # The script expects an explicit output file path via ``-o``.
    # We generate a unique file name for each URL so that parallel runs
    # never clash.
    timestamp = int(time.time() * 1000)
    out_file = out_dir / f"{timestamp}.sssom.tsv"

    cmd = [
        sys.executable,               # use the same interpreter that runs this test
        str(script_path),
        url,
        "-y",                         # auto‑accept any prompts
        "--no-edit",                  # never open an editor
        "-o",
        str(out_file),
    ]

    logging.debug("Running command (cwd=%s): %s", src_dir, " ".join(cmd))

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        cmd,
        cwd=src_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    return {
        "url": url,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "generated_file": str(out_file) if result.returncode == 0 else None,
    }


def _write_report(report_path: Path, results: List[Dict[str, str]]) -> None:
    """Write a JSON summary (`report.json`) into the temporary directory."""
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "total": len(results),
        "succeeded": sum(1 for r in results if r["returncode"] == 0),
        "failed": sum(1 for r in results if r["returncode"] != 0),
        "details": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2, sort_keys=True)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )


# ----------------------------------------------------------------------
# Main driver
# ----------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read URLs from test_urls.txt, invoke write_sssom_file.py for each "
            "URL (non‑interactive), and produce a JSON report."
        )
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable DEBUG logging.")
    parser.add_argument(
        "--clean-up",
        action="store_true",
        help="Delete the temporary directory after the run (default: keep it).",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Alias for the default behaviour (keeps the temp dir).",
    )
    args = parser.parse_args()
    _setup_logging(args.verbose)

    # ------------------------------------------------------------------
    # Locate the URLs file
    # ------------------------------------------------------------------
    test_dir = Path(__file__).parent            # ./test
    urls_file = test_dir / "test_urls.txt"

    if not urls_file.is_file():
        logging.error("Cannot find %s – aborting.", urls_file)
        return 1

    urls = _load_urls(urls_file)
    if not urls:
        logging.warning("URL list is empty – nothing to do.")
        return 0

    # ------------------------------------------------------------------
    # Create a temporary output directory for this run
    # ------------------------------------------------------------------
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    tmp_root = test_dir / f"tmp-sssom-run-{timestamp}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    logging.info("Temporary output directory: %s", tmp_root)

    # ------------------------------------------------------------------
    # Process each URL
    # ------------------------------------------------------------------
    results: List[Dict[str, str]] = []
    src_dir = Path(__file__).parents[1] / "src"   # ../../src

    for idx, url in enumerate(urls, start=1):
        logging.info("Processing %03d/%03d – %s", idx, len(urls), url)
        try:
            result = _run_write_sssom(src_dir=src_dir, url=url, out_dir=tmp_root)
        except Exception as exc:                 # unexpected Python‑level error
            logging.exception("Unexpected exception for %s", url)
            result = {
                "url": url,
                "returncode": -1,
                "stdout": "",
                "stderr": str(exc),
                "generated_file": None,
            }

        # Per‑URL concise log line
        if result["returncode"] == 0:
            logging.info("✔ SUCCESS – file written to %s", result["generated_file"])
        else:
            # Show only the first few lines of stderr to keep the console tidy
            short_err = "\n".join(result["stderr"].splitlines()[:3])
            logging.error(
                "✘ FAILURE (rc=%s) – stderr: %s", result["returncode"], short_err
            )

        results.append(result)

    # ------------------------------------------------------------------
    # Write the JSON report (this file will stay on disk)
    # ------------------------------------------------------------------
    report_path = tmp_root / "report.json"
    _write_report(report_path, results)
    logging.info("JSON report written to %s", report_path)

    # ------------------------------------------------------------------
    # Clean‑up (optional)
    # ------------------------------------------------------------------
    if args.clean_up:
        try:
            shutil.rmtree(tmp_root)
            logging.debug("Removed temporary directory %s", tmp_root)
        except Exception as exc:  # pragma: no cover
            logging.warning("Could not delete %s – %s", tmp_root, exc)

    # ------------------------------------------------------------------
    # Exit status – 0 if every URL succeeded, 1 otherwise (good for CI)
    # ------------------------------------------------------------------
    any_failed = any(r["returncode"] != 0 for r in results)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())