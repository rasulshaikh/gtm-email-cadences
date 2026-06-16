# GTM Email Cadences — MiniMax AI

23 signal-led, persona-specific email cadences powered by MiniMax AI. Each cadence has 3-4 emails, a specific trigger, and a personalization hook generated on the fly.

## What's included

| Group | Cadences |
|-------|----------|
| Signal (8) | Series A, Series B/C, New VP Sales, Hiring SDRs, Hiring RevOps, Tech stack change, Product launch, Market expansion |
| Persona (7) | VP Sales, CRO, CMO, RevOps, Founder/CEO, SDR Manager, Head of Growth |
| Vertical (4) | B2B SaaS, Fintech, Cybersecurity/CISO, Marketplace |
| Stage (4) | Re-engagement, Breakup, Post-demo no decision, Champion mobilizer |

## How it works

1. You pick a cadence matching the signal or persona
2. MiniMax generates a specific opening hook from the prospect's context
3. The runner fills all merge tags and outputs a ready-to-send sequence

The hook is generated via a completion-style prompt: `"Saw {Company}..."` — forces brevity and specificity, no generic flattery.

## Setup

```bash
pip install -r requirements.txt
export MINIMAX_API_KEY=your_key_here
```

## Usage

**List all cadences:**
```bash
python cadence_runner.py list
```

**Run for a single lead:**
```bash
python cadence_runner.py run \
  --cadence cadences/signal/01_funding_series_a.yaml \
  --first-name Sarah \
  --company "Acme Corp" \
  --context "just raised Series A of $8M led by Sequoia" \
  --your-name "Rasul"
```

**Skip AI hook generation (faster, uses template fallback):**
```bash
python cadence_runner.py run \
  --cadence cadences/persona/13_founder_ceo.yaml \
  --first-name James \
  --company "BuildFast" \
  --context "" \
  --your-name "Rasul" \
  --no-ai
```

**Batch from CSV:**
```bash
python cadence_runner.py batch \
  --cadence cadences/signal/04_hiring_sdrs.yaml \
  --input example_leads.csv \
  --output sequences.csv \
  --your-name "Rasul"
```

## Merge tags

All templates support these tokens:

| Token | Source |
|-------|--------|
| `{{first_name}}` | Lead data |
| `{{company}}` | Lead data |
| `{{persona_hook}}` | MiniMax generated |
| `{{your_name}}` | CLI flag |
| `{{your_title}}` | CLI flag (default: GTM Engineer) |
| `{{trigger}}`, `{{new_tool}}`, `{{funding_stage}}` | Lead CSV columns |

Any column in your input CSV becomes a usable token automatically.

## Cadence format

Each cadence is a YAML file you can read, edit, or clone:

```yaml
name: Series A Funding Trigger
trigger: Company just raised Series A
persona: Founder / VP Sales
when_to_use: Within 72 hours of funding announcement.
sequence_length: 4 emails

emails:
  - step: 1
    delay_days: 0
    subject: "{{company}}'s Series A"
    body: |
      {{persona_hook}}

      The motion that gets a company to Series A rarely scales...
```

## Picking the right cadence

```
Signal available? → Use signal/ cadence (highest relevance)
No signal, know persona? → Use persona/ cadence
Know the vertical? → Use vertical/ cadence
End of sequence? → Use stage/21_breakup.yaml
Post-demo gone quiet? → Use stage/22_post_demo_no_decision.yaml
Talking to wrong person? → Use stage/23_champion_mobilizer.yaml
```

## Model

Uses `MiniMax-Text-01` for hook generation — fast, no reasoning blocks, good at constrained creative tasks. Switch to `MiniMax-M1` in `cadence_runner.py` if you want reasoning-backed hooks.

## Cost

MiniMax-Text-01 hook generation: ~$0.001 per lead. A 1,000-lead batch costs ~$1.
