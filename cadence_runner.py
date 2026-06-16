#!/usr/bin/env python3
"""
GTM Email Cadence Runner — powered by MiniMax M1
Loads a YAML cadence, generates a personalized hook via MiniMax,
fills all merge tags, and outputs a ready-to-send email sequence.

Usage:
    # Single lead
    python cadence_runner.py run \
        --cadence cadences/signal/01_funding_series_a.yaml \
        --first-name Sarah \
        --company "Acme Corp" \
        --context "just raised Series A of $8M led by Sequoia" \
        --your-name "Rasul" \
        --your-title "GTM Engineer"

    # Batch from CSV
    python cadence_runner.py batch \
        --cadence cadences/persona/09_vp_sales.yaml \
        --input leads.csv \
        --output sequences.csv

    # List all available cadences
    python cadence_runner.py list
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests
import yaml

MINIMAX_API_URL = "https://api.minimaxi.chat/v1/chat/completions"
MINIMAX_MODEL = "MiniMax-Text-01"   # generative model — no think blocks, better for copy
MINIMAX_MODEL_REASONING = "MiniMax-M1"  # reasoning model — use for analysis tasks

HOOK_SYSTEM_PROMPT = """Output: exactly one sentence. No subject line. No greeting. No explanation.

The sentence is an observation about the company. It references a specific fact from the context. It does NOT compliment, congratulate, or express excitement.

Examples of what to output:
"Saw Acme closed a Sequoia-led $8M round right as the team was scaling past 50 people."
"Noticed BuildFast posted 4 SDR roles in the last two weeks — classic growth inflection."
"Saw CloudOps just migrated to HubSpot after running on Pipedrive for 3 years."

Output format: one sentence, no punctuation beyond a period, no quotes around it."""


def call_minimax(prompt: str, system: str = HOOK_SYSTEM_PROMPT) -> str:
    """Call MiniMax M1 and return the text response (strips <think> tags)."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise ValueError("MINIMAX_API_KEY not set")

    payload = {
        "model": MINIMAX_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(MINIMAX_API_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]

    # Strip <think> blocks if using a reasoning model (MiniMax-M1)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return cleaned if cleaned else text.strip()


def generate_hook(
    company: str,
    first_name: str,
    context: str,
    cadence_trigger: str,
    persona: str,
) -> str:
    """Generate a personalized opening hook via MiniMax."""
    # Completion-style prompt: give the opener word, model fills in the rest.
    # Forces brevity and correct voice — model can't write a greeting or subject line.
    starter = "Saw" if "launch" not in cadence_trigger.lower() and "expansion" not in cadence_trigger.lower() else "Noticed"
    prompt = (
        f'Complete this cold email opening line in under 12 words. '
        f'Use only the specific facts below. No filler words.\n\n'
        f'"{starter} {company}...' + '"\n\n'
        f"Facts: {context}. Trigger: {cadence_trigger}.\n\n"
        f'Output only the completed sentence starting with "{starter} {company}".'
    )
    raw = call_minimax(prompt)

    # Extract only the completed sentence
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    for line in lines:
        if line.lower().startswith(starter.lower()) or company.lower() in line.lower():
            first = re.split(r'(?<=[.!?])\s', line)[0].strip()
            return first

    # Fallback: first non-empty line, first sentence
    text = lines[0] if lines else raw.strip()
    return re.split(r'(?<=[.!?])\s', text)[0].strip()


def fill_template(template: str, variables: dict) -> str:
    """Replace {{token}} placeholders with values from variables dict."""
    def replacer(match):
        key = match.group(1).strip()
        return str(variables.get(key, match.group(0)))

    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


def load_cadence(path: str) -> dict:
    """Load and parse a YAML cadence file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_single(
    cadence_path: str,
    first_name: str,
    company: str,
    context: str,
    your_name: str,
    your_title: str = "GTM Engineer",
    extra_vars: Optional[dict] = None,
    generate_hook_flag: bool = True,
) -> list[dict]:
    """Run a cadence for a single lead. Returns list of email dicts."""
    cadence = load_cadence(cadence_path)

    variables = {
        "first_name": first_name,
        "company": company,
        "your_name": your_name,
        "your_title": your_title,
        **(extra_vars or {}),
    }

    if generate_hook_flag:
        print(f"  Generating hook for {first_name} @ {company}...", end=" ", flush=True)
        hook = generate_hook(
            company=company,
            first_name=first_name,
            context=context or f"reached out about {cadence.get('trigger', 'GTM')}",
            cadence_trigger=cadence.get("trigger", ""),
            persona=cadence.get("persona", ""),
        )
        variables["persona_hook"] = hook
        print("done")
    else:
        variables["persona_hook"] = f"Saw what {company} is working on and wanted to reach out."

    emails = []
    for email in cadence.get("emails", []):
        step_key = str(email.get("step", ""))
        if "_alt_" in step_key:
            continue  # skip alt variants in default run

        emails.append({
            "step": email["step"],
            "delay_days": email.get("delay_days", 0),
            "subject": fill_template(email.get("subject", ""), variables),
            "body": fill_template(email.get("body", ""), variables).strip(),
            "cadence": cadence.get("name", ""),
        })

    return emails


def process_batch(
    cadence_path: str,
    input_csv: str,
    output_csv: str,
    your_name: str,
    your_title: str = "GTM Engineer",
    delay: float = 1.0,
) -> None:
    """Process a CSV of leads through a cadence."""
    cadence = load_cadence(cadence_path)

    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        base_fields = reader.fieldnames or []

    max_steps = len([e for e in cadence.get("emails", []) if "_alt_" not in str(e.get("step", ""))])
    output_fields = (
        ["company", "first_name", "persona_hook"]
        + [f"email_{i+1}_subject" for i in range(max_steps)]
        + [f"email_{i+1}_body" for i in range(max_steps)]
        + [f"email_{i+1}_delay_days" for i in range(max_steps)]
    )

    results = []
    for i, row in enumerate(rows, 1):
        company = row.get("company") or row.get("Company") or ""
        first_name = row.get("first_name") or row.get("First Name") or "there"
        context = row.get("context") or row.get("signal") or row.get("Signal") or ""

        print(f"[{i}/{len(rows)}] {first_name} @ {company}")

        try:
            emails = run_single(
                cadence_path=cadence_path,
                first_name=first_name,
                company=company,
                context=context,
                your_name=your_name,
                your_title=your_title,
                extra_vars={k: v for k, v in row.items()},
            )
            out_row = {"company": company, "first_name": first_name}
            out_row["persona_hook"] = next(
                (e["body"].split("\n")[0] for e in emails if e["step"] == 1), ""
            )
            for j, email in enumerate(emails):
                out_row[f"email_{j+1}_subject"] = email["subject"]
                out_row[f"email_{j+1}_body"] = email["body"]
                out_row[f"email_{j+1}_delay_days"] = email["delay_days"]
        except Exception as e:
            print(f"  ERROR: {e}")
            out_row = {"company": company, "first_name": first_name, "persona_hook": f"ERROR: {e}"}

        results.append(out_row)
        if i < len(rows):
            time.sleep(delay)

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDone. {len(results)} sequences written → {output_csv}")


def list_cadences() -> None:
    """Print all available cadences."""
    root = Path(__file__).parent / "cadences"
    groups = ["signal", "persona", "vertical", "stage"]
    total = 0
    for group in groups:
        files = sorted((root / group).glob("*.yaml"))
        if not files:
            continue
        print(f"\n{group.upper()}")
        for f in files:
            try:
                data = yaml.safe_load(f.read_text())
                name = data.get("name", f.stem)
                trigger = data.get("trigger", "")[:70]
                steps = len([e for e in data.get("emails", []) if "_alt_" not in str(e.get("step", ""))])
                print(f"  {f.name:<42} {name} ({steps} emails)")
                print(f"  {'':42} Trigger: {trigger}")
                total += 1
            except Exception as e:
                print(f"  {f.name}: parse error — {e}")
    print(f"\nTotal: {total} cadences")


def main() -> None:
    parser = argparse.ArgumentParser(description="GTM Email Cadence Runner (MiniMax M1)")
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Run cadence for a single lead")
    run_p.add_argument("--cadence", required=True, help="Path to YAML cadence file")
    run_p.add_argument("--first-name", required=True)
    run_p.add_argument("--company", required=True)
    run_p.add_argument("--context", default="", help="Signal or context about this company")
    run_p.add_argument("--your-name", required=True)
    run_p.add_argument("--your-title", default="GTM Engineer")
    run_p.add_argument("--no-ai", action="store_true", help="Skip MiniMax hook generation")

    batch_p = sub.add_parser("batch", help="Run cadence for a CSV of leads")
    batch_p.add_argument("--cadence", required=True)
    batch_p.add_argument("--input", required=True, help="Input CSV")
    batch_p.add_argument("--output", default="sequences.csv")
    batch_p.add_argument("--your-name", required=True)
    batch_p.add_argument("--your-title", default="GTM Engineer")
    batch_p.add_argument("--delay", type=float, default=1.0, help="Seconds between API calls")

    sub.add_parser("list", help="List all available cadences")

    args = parser.parse_args()

    if args.cmd == "run":
        emails = run_single(
            cadence_path=args.cadence,
            first_name=args.first_name,
            company=args.company,
            context=args.context,
            your_name=args.your_name,
            your_title=args.your_title,
            generate_hook_flag=not args.no_ai,
        )
        for email in emails:
            print(f"\n{'='*60}")
            print(f"Email {email['step']} (send on day {email['delay_days']})")
            print(f"Subject: {email['subject']}")
            print(f"\n{email['body']}")
        print(f"\n{'='*60}")
        print(f"Cadence: {emails[0]['cadence']} — {len(emails)} emails")

    elif args.cmd == "batch":
        process_batch(
            cadence_path=args.cadence,
            input_csv=args.input,
            output_csv=args.output,
            your_name=args.your_name,
            your_title=args.your_title,
            delay=args.delay,
        )

    elif args.cmd == "list":
        list_cadences()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
