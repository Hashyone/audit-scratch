#!/usr/bin/env python3
"""
scaffold_test.py — Foundry PoC/fuzz scaffolding. The final stage.

Completes the pipeline:
    scope_gate.py -> generate.py -> disprove.py -> scaffold_test.py -> Foundry

This is the stage that was missing: turning a CONFIRMED BREAK verdict from
disprove.py into an actual runnable Foundry test, grounded in the real
repo's existing test conventions via read-only tool access — not a generic
template that ignores how the codebase is actually structured.

This script does NOT generate new hypotheses and does NOT re-verify the
bug's arithmetic — it trusts the CONFIRMED BREAK verdict it's given and
focuses narrowly on expressing that exact counterexample as Solidity test
code. If you haven't run disprove.py and gotten a real CONFIRMED BREAK
verdict, this script will refuse to run by default.

Like generate.py and disprove.py, this is READ-ONLY against the repo
(list_files/read_file/grep_files via repo_tools.py). It outputs a .t.sol
file for YOU to review and run yourself with `forge test` — it does not
execute forge, does not write directly into your repo's test directory,
and does not loop on test failures. That's a deliberate boundary: an
agentic write+execute+retry loop here would burn API spend and compute
chasing a test that might not even be expressing the right counterexample,
faster than you could review it. Review the output, drop it into your
repo's test dir yourself, run forge test yourself.

Usage:
    python scaffold_test.py --program origin --target VaultCore.sol,VaultAdmin.sol \\
        --disprove-result findings/origin/disprove_20260622T101500Z.md \\
        --repo-root /workspaces/codespaces-blank/dss/origin-dollar
"""

import argparse
import datetime
import json
import os
import re
import sys

from dotenv import load_dotenv

import repo_tools

load_dotenv()

PROMPT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "prompts", "scaffold_test.txt")
POCS_DIR = os.path.join(os.path.dirname(__file__), "pocs")
SCOPE_CACHE_DIR = os.path.join(os.path.dirname(__file__), "scope_cache")
MAX_TOOL_ROUNDS = 15  # needs to read existing test files/patterns, similar budget to generate.py


def check_gate_was_run(program: str) -> bool:
    checklist = os.path.join(SCOPE_CACHE_DIR, program, "PRE_WORK_CHECKLIST.md")
    if not os.path.exists(checklist):
        return False
    with open(checklist, "r", encoding="utf-8") as f:
        content = f.read()
    return content.count("- [ ]") == 0


def extract_verdict(disprove_text: str) -> str | None:
    """Find the verdict line in a disprove.py output file. Returns the
    verdict keyword or None if no clear verdict is found."""
    for line in disprove_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("CONFIRMED BREAK"):
            return "CONFIRMED BREAK"
        if stripped.startswith("DISPROVEN"):
            return "DISPROVEN"
        if stripped.startswith("HOLDS UNDER TESTED RANGE"):
            return "HOLDS UNDER TESTED RANGE"
    return None


def read_file_or_empty(path: str | None) -> str:
    if not path:
        return "(none provided)"
    if not os.path.exists(path):
        print(f"  WARNING: {path} not found, treating as empty.", file=sys.stderr)
        return "(none provided)"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_prompt(confirmed_hypothesis: str, counterexample: str, target_files: str) -> str:
    with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()
    return (
        template
        .replace("{{CONFIRMED_HYPOTHESIS}}", confirmed_hypothesis)
        .replace("{{COUNTEREXAMPLE}}", counterexample)
        .replace("{{TARGET_FILES}}", target_files)
    )


def call_deepseek(prompt: str, repo_root: str | None) -> str:
    from openai import OpenAI
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set in environment/.env", file=sys.stderr)
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    system_msg = (
        "You are a meticulous smart contract security researcher writing Foundry "
        "tests. Precision and correctness matter far more than creativity here — "
        "you are proving an already-confirmed bug, not finding a new one. "
        "Always respond in English."
    )
    if repo_root:
        system_msg += (
            " You have READ-ONLY tools (list_files, read_file, grep_files) scoped to "
            "the target repo. Use them to find existing test files and match the "
            "repo's real conventions (base test contracts, fork setup, mock patterns) "
            "before writing your test. You cannot write files or run forge yourself — "
            "output the complete test file as text in your final answer."
        )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ]

    # Low temperature, matching disprove.py's reasoning: this stage wants
    # precise, repeatable Solidity that matches real repo conventions, not
    # creative variation. generate.py's high temperature does not apply here.
    kwargs = {"model": "deepseek-chat", "messages": messages, "temperature": 0.2}
    if repo_root:
        kwargs["tools"] = repo_tools.TOOL_SCHEMAS

    rounds = 0
    while True:
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        if not getattr(msg, "tool_calls", None):
            return msg.content or ""

        rounds += 1
        if rounds > MAX_TOOL_ROUNDS:
            print(f"  WARNING: hit MAX_TOOL_ROUNDS ({MAX_TOOL_ROUNDS}) — forcing final answer.", file=sys.stderr)
            messages.append({"role": "user", "content": "You've used your tool budget. Write the best test you can now with what you've already read, or report COULD NOT REPRODUCE if you don't have enough context."})
            kwargs["tools"] = None
            kwargs["messages"] = messages
            continue

        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}
            print(f"  [tool call] {fn_name}({fn_args})")
            result = repo_tools.dispatch_tool_call(repo_root, fn_name, fn_args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)[:50_000]})
        kwargs["messages"] = messages


def extract_solidity_block(text: str) -> str | None:
    """Pull the first ```solidity or ```sol fenced code block out of the
    model's response, for convenience when writing the standalone .t.sol
    file. Returns None if no fenced Solidity block is found — caller
    should fall back to saving the full response as markdown instead."""
    match = re.search(r"```(?:solidity|sol)\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else None


def main():
    ap = argparse.ArgumentParser(description="Foundry PoC/fuzz test scaffolding — final pipeline stage")
    ap.add_argument("--program", required=True)
    ap.add_argument("--target", required=True, help="Comma-separated target files")
    ap.add_argument("--disprove-result", required=True,
                     help="Path to a disprove.py output file (findings/<program>/disprove_*.md) "
                          "containing a CONFIRMED BREAK verdict.")
    ap.add_argument("--repo-root", default=None,
                     help="Local repo clone path for read-only tool access. Strongly recommended — "
                          "without it the test won't match the repo's real conventions.")
    ap.add_argument("--provider", choices=["deepseek"], default="deepseek",
                     help="Only deepseek is wired for tool calls currently.")
    ap.add_argument("--skip-gate-check", action="store_true")
    ap.add_argument("--force", action="store_true",
                     help="Proceed even if the disprove-result file's verdict isn't CONFIRMED BREAK. "
                          "Not recommended — scaffolding a test for a DISPROVEN or inconclusive "
                          "hypothesis wastes the same cycles this whole pipeline exists to avoid.")
    args = ap.parse_args()

    if not args.skip_gate_check and not check_gate_was_run(args.program):
        print(f"⚠️  PRE_WORK_CHECKLIST.md for '{args.program}' is missing or has unchecked items.")
        confirm = input("   Type 'I have manually confirmed scope and known issues' to proceed anyway: ")
        if confirm.strip() != "I have manually confirmed scope and known issues":
            print("Aborting. Run scope_gate.py first.")
            sys.exit(1)

    disprove_text = read_file_or_empty(args.disprove_result)
    if disprove_text == "(none provided)":
        print(f"ERROR: could not read --disprove-result file: {args.disprove_result}", file=sys.stderr)
        sys.exit(1)

    verdict = extract_verdict(disprove_text)
    if verdict != "CONFIRMED BREAK":
        print(f"⚠️  Verdict in {args.disprove_result} is '{verdict or 'NOT FOUND'}', not CONFIRMED BREAK.")
        print("   Scaffolding a Foundry test only makes sense once a hypothesis survives")
        print("   rigorous disproof. Building a test for a DISPROVEN or inconclusive claim")
        print("   wastes the same cycles disprove.py exists to save you.")
        if not args.force:
            print("   Re-run with --force if you have a specific reason to proceed anyway.")
            sys.exit(1)
        print("   --force given, proceeding anyway.")

    if args.repo_root and not os.path.isdir(args.repo_root):
        print(f"ERROR: --repo-root '{args.repo_root}' is not a directory.", file=sys.stderr)
        sys.exit(1)
    if not args.repo_root:
        print("⚠️  No --repo-root given. The test won't be grounded in the repo's real test")
        print("   conventions (base contracts, fork setup, mocks) and may not actually compile")
        print("   or run as-is. Strongly recommend re-running with --repo-root.\n")

    # The whole disprove_*.md file is passed as both hypothesis and
    # counterexample context — disprove.py's output already separates these
    # conceptually in its prose, and re-parsing it heuristically here risks
    # losing nuance the model needs. Let the model itself extract what it
    # needs from the full verdict text.
    confirmed_hypothesis = disprove_text
    counterexample = disprove_text  # same source; prompt asks the model to focus on the verdict section

    prompt = build_prompt(confirmed_hypothesis, counterexample, args.target)

    print(f"=== Scaffolding Foundry test for {args.program} / {args.target} ===")
    if args.repo_root:
        print(f"=== Repo read-access enabled at: {args.repo_root} ===\n")
    else:
        print()

    result = call_deepseek(prompt, repo_root=args.repo_root)
    print(result)

    if "COULD NOT REPRODUCE" in result.upper():
        print("\n⚠️  Model reported it could NOT reproduce the counterexample as a real test.")
        print("   This is the correct, honest outcome when the bug can't actually be expressed")
        print("   as working code — do not force it. Re-check the original disprove.py verdict;")
        print("   the precondition might have been missed there too.")

    program_dir = os.path.join(POCS_DIR, args.program)
    os.makedirs(program_dir, exist_ok=True)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")

    full_out_path = os.path.join(program_dir, f"scaffold_{ts}.md")
    with open(full_out_path, "w", encoding="utf-8") as f:
        f.write(f"# Test scaffold run: {args.program} / {args.target}\n\n")
        f.write(f"Run at: {ts}\nSource disprove result: {args.disprove_result}\n\n")
        f.write("## Full model output\n\n")
        f.write(result + "\n")
    print(f"\n=== Full response saved to {full_out_path} ===")

    sol_code = extract_solidity_block(result)
    if sol_code:
        sol_path = os.path.join(program_dir, f"PoC_{ts}.t.sol")
        with open(sol_path, "w", encoding="utf-8") as f:
            f.write(sol_code + "\n")
        print(f"=== Extracted Solidity test saved separately to {sol_path} ===")
        print("    Review it, then copy into your repo's test directory and run forge test yourself.")
    else:
        print("=== No fenced ```solidity code block found in the response — check the .md file ===")
        print("    above for the test code; it may be formatted differently than expected.")


if __name__ == "__main__":
    main()
