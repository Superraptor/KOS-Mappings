#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
review_sssom_metadata.py

A tiny helper that runs ``generate_sssom_metadata.py`` on a given file path
or URL, shows the produced SSSOM‑metadata to the user, lets the user edit
or confirm it, adds reviewer information and finally emits the (optionally
edited) JSON.

Typical usage::

    python review_sssom_metadata.py path/to/resource.tsv
    python review_sssom_metadata.py https://github.com/owner/repo/raw/main/mappings.sssom -o reviewed.json
    python review_sssom_metadata.py data.xlsx --no-edit   # accept without opening an editor

The script only depends on the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root and src directory are on sys.path
_SRC_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SRC_DIR.parent
for d in [str(_SRC_DIR), str(_ROOT_DIR)]:
    if d not in sys.path:
        sys.path.insert(0, d)

# ---------------------------------------------------------------------------
# 1️⃣  RUN THE METADATA‑GENERATION SCRIPT
# ---------------------------------------------------------------------------

def _run_generate_metadata(input_location: str) -> Dict[str, Any]:
    """
    Calls generate_metadata directly or via subprocess, returns the parsed SSSOM document dict.
    """
    try:
        from src.generate_sssom_metadata import generate_metadata
        return generate_metadata(input_location)
    except Exception as exc:
        try:
            from generate_sssom_metadata import generate_metadata
            return generate_metadata(input_location)
        except Exception:
            pass

    script_path = Path(__file__).with_name("generate_sssom_metadata.py")
    cmd = [sys.executable, str(script_path), input_location]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_SRC_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Could not locate `generate_sssom_metadata.py`. Make sure it is in the "
            "same directory or on your PATH."
        ) from exc

    if result.returncode != 0:
        # Include the script's stderr in the error message – it usually contains
        # a helpful traceback.
        raise RuntimeError(
            f"`generate_sssom_metadata.py` exited with status {result.returncode}.\n"
            f"Stderr:\n{result.stderr}"
        )

    # The script is expected to emit a *single* JSON document.
    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Failed to decode JSON output from `generate_sssom_metadata.py`. "
            "The output was:\n" + result.stdout
        ) from exc

    return metadata


# ---------------------------------------------------------------------------
# 2️⃣  INTERACTIVE EDITING HELPERS
# ---------------------------------------------------------------------------

def _open_in_editor(initial_json: str, editor_cmd: Optional[str] = None) -> str:
    """
    Writes *initial_json* to a temporary file, opens the file in the user's
    editor, then returns the possibly edited content.

    The editor is taken from:
        1. ``editor_cmd`` argument (if supplied)
        2. ``$EDITOR`` environment variable
        3. Fallback to ``vi`` on Unix or ``notepad`` on Windows.
    """
    if editor_cmd is None:
        editor_cmd = os.getenv("EDITOR")
        if not editor_cmd:
            if os.name == "nt":
                editor_cmd = "notepad"
            else:
                editor_cmd = "vi"

    # Create a temporary file that will survive the editor session.
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".json", delete=False, encoding="utf-8"
    ) as tf:
        tf_path = Path(tf.name)
        tf.write(initial_json)
        tf.flush()   # make sure everything is written before launching the editor

    # Launch the editor – we use ``subprocess.call`` so that the script
    # waits until the editor is closed.
    try:
        subprocess.call([editor_cmd, str(tf_path)])
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Editor command `{editor_cmd}` not found. Set $EDITOR to a valid program."
        ) from exc

    # Read the possibly‑modified file back.
    edited_content = tf_path.read_text(encoding="utf-8")
    # Clean up the temp file.
    tf_path.unlink(missing_ok=True)

    return edited_content


def _pretty_print(metadata: Dict[str, Any]) -> None:
    print("\n--- GENERATED SSSOM METADATA -----------------------------------")
    display_meta = dict(metadata)
    mappings = display_meta.get("mappings", [])
    if isinstance(mappings, list) and len(mappings) > 20:
        display_meta["mappings"] = f"<{len(mappings)} mapping rows (sample of first 3 shown below)>"
        display_meta["_mappings_sample"] = mappings[:3]
    print(json.dumps(display_meta, indent=2, ensure_ascii=False))
    print("--- END OF METADATA -------------------------------------------\n")


# ---------------------------------------------------------------------------
# 3️⃣  COLLECT REVIEWER INFORMATION
# ---------------------------------------------------------------------------

def _gather_reviewer_info(auto_accept: bool = False) -> Dict[str, str]:
    """
    Prompts the user for reviewer name, e‑mail and review date.
    When auto_accept is True, provides automated reviewer defaults without prompting.
    """
    today_iso = date.today().isoformat()
    if auto_accept:
        return {
            "reviewer": "Automated Pipeline",
            "email": "pipeline@mapping-commons.org",
            "date": today_iso,
        }

    print("Please provide reviewer information (will be stored under the key `review`).")
    name = input("  Reviewer name   : ").strip()
    while not name:
        print("    → Name may not be empty.")
        name = input("  Reviewer name   : ").strip()

    email = input("  Reviewer e‑mail : ").strip()
    while not email:
        print("    → E‑mail may not be empty.")
        email = input("  Reviewer e‑mail : ").strip()

    rev_date = input(f"  Review date [{today_iso}] : ").strip()
    if not rev_date:
        rev_date = today_iso

    try:
        datetime.fromisoformat(rev_date)
    except ValueError:
        print("    → Invalid date format – keeping today’s date.")
        rev_date = today_iso

    return {
        "reviewer": name,
        "email": email,
        "date": rev_date,
    }


# ---------------------------------------------------------------------------
# 3️⃣  MAIN LOGIC – RUN, DISPLAY, (optionally) EDIT, ADD REVIEW INFO
# ---------------------------------------------------------------------------

def review_metadata(
    input_location: str,
    *,
    output_path: Optional[Path] = None,
    editor: Optional[str] = None,
    auto_accept: bool = False,
    no_edit: bool = False,
    emit_stdout: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrates the whole review process.

    Parameters
    ----------
    input_location:
        File system path or URL that should be fed to ``generate_sssom_metadata.py``.
    output_path:
        If supplied, the final JSON is written to this file; otherwise it is
        printed to ``stdout``.
    editor:
        Explicit editor command (overrides $EDITOR).
    auto_accept:
        If ``True`` the script **does not** ask the “confirm?” question – it
        proceeds as if the user typed “y”.
    no_edit:
        If ``True`` the metadata is accepted *as‑is* – the editor is never opened.

    Returns
    -------
    The final (reviewed) metadata dictionary.
    """
    # -----------------------------------------------------------------------
    # 1️⃣  Generate the raw metadata
    # -----------------------------------------------------------------------
    raw_metadata = _run_generate_metadata(input_location)

    # -----------------------------------------------------------------------
    # 2️⃣  Show it to the user
    # -----------------------------------------------------------------------
    _pretty_print(raw_metadata)

    # -----------------------------------------------------------------------
    # 3️⃣  Ask whether the user wants to edit it (unless ``--no-edit`` was used)
    # -----------------------------------------------------------------------
    edited_metadata = raw_metadata
    if not no_edit:
        edit_answer = "y"
        if not auto_accept:
            edit_answer = input("Do you want to edit the metadata? (y/N) ").strip().lower()
        if edit_answer == "y":
            # Dump to a nicely‑indented string, open the editor, then load back.
            json_str = json.dumps(raw_metadata, indent=2, ensure_ascii=False)
            edited_str = _open_in_editor(json_str, editor_cmd=editor)

            try:
                edited_metadata = json.loads(edited_str)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "Edited content is not valid JSON. Aborting.\n"
                    f"Error: {exc}\nEdited text was:\n{edited_str}"
                ) from exc

            print("\n✅ Edited metadata loaded successfully.\n")
        else:
            print("✅ Keeping the generated metadata unchanged.\n")
    else:
        print("✅ Editing disabled – using generated metadata as‑is.\n")

    # -----------------------------------------------------------------------
    # 4️⃣  Gather reviewer information and embed it
    # -----------------------------------------------------------------------
    reviewer_info = _gather_reviewer_info(auto_accept=auto_accept)
    # We store the review block under a top‑level key called ``review``.
    # If a ``review`` key already exists we simply overwrite it (the reviewer
    # is expected to be the *last* person to touch the file).
    edited_metadata["review"] = reviewer_info

    # -----------------------------------------------------------------------
    # 5️⃣  Emit the final JSON
    # -----------------------------------------------------------------------
    if output_path:
        final_json = json.dumps(edited_metadata, indent=2, ensure_ascii=False)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(final_json, encoding="utf-8")
        print(f"✅ Reviewed metadata written to: {output_path}")
    elif emit_stdout:
        final_json = json.dumps(edited_metadata, indent=2, ensure_ascii=False)
        # Print to stdout – useful for piping into another tool.
        print(final_json)

    # Return the dict for callers that may want to reuse it programmatically.
    return edited_metadata


# ---------------------------------------------------------------------------
# 6️⃣  COMMAND‑LINE INTERFACE
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="review_sssom_metadata.py",
        description=(
            "Run `generate_sssom_metadata.py` on a file path or URL, let the user "
            "review/confirm the produced SSSOM metadata and add reviewer info."
        ),
    )
    parser.add_argument(
        "location",
        metavar="INPUT",
        help="File path or URL that should be processed by generate_sssom_metadata.py",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write the final, reviewed metadata to this file (default: stdout)",
    )
    parser.add_argument(
        "-e",
        "--editor",
        help="Explicit editor command (overrides $EDITOR). Ignored if --no-edit is set.",
    )
    parser.add_argument(
        "--no-edit",
        action="store_true",
        help="Skip opening an editor – accept the generated metadata as‑is",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Assume “yes” to all prompts (accept generated metadata without asking)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable DEBUG‑level logging (useful when something goes wrong)",
    )
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()

    # -----------------------------------------------------------------------
    # Logging – we keep it very light; the script only uses the stdlib.
    # -----------------------------------------------------------------------
    log_level = "DEBUG" if args.verbose else "INFO"
    import logging
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger = logging.getLogger(__name__)

    try:
        # -------------------------------------------------------------------
        # Run the generation script and start the interactive review.
        # -------------------------------------------------------------------
        final_metadata = review_metadata(
            args.location,
            output_path=args.output,
            editor=args.editor,
            auto_accept=args.yes,
            no_edit=args.no_edit,
            emit_stdout=True,
        )
        # ``review_metadata`` already printed the result (or wrote it to a file).
        # Returning 0 signals success to the shell.
        return 0
    except RuntimeError as exc:
        logger.error("❌  %s", exc)
        return 1
    except KeyboardInterrupt:          # pragma: no cover
        logger.warning("Interrupted by user")
        return 1


if __name__ == "__main__":
    sys.exit(main())