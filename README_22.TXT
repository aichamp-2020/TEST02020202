# Model Advisor

A command-line tool that recommends which LLM to use for a given task — describe a use case in plain English, get a ranked recommendation with reasoning. Built around an insurance-industry use case library, but the scoring logic is general-purpose.

No dependencies. Standard library only. Works with Python 3.9+.

## What it covers

- **26 models across 12 vendors**: Anthropic (Claude), OpenAI (GPT), Google (Gemini), Meta (Llama), DeepSeek, Mistral, Microsoft (Phi), Cohere (Command), Alibaba (Qwen), xAI (Grok), Amazon (Nova), IBM (Granite) — including GPT-4.1 (the prior-generation GPT-4 class flagship, still widely deployed in Azure enterprise agreements) and a dedicated Small Language Model (SLM) tier (Gemma 4 E4B, Llama 3.2 3B, Qwen3.5 9B, Ministral 3 8B, Granite 4.1 8B).
- **11 parameters per model**: Intelligence Index, output speed, time to first token, input/output/blended/cache-hit price, context window, knowledge cutoff, release date, eval cost, open-weight status
- **Modality support**: image input (OCR/documents), native audio input, native video input, image generation — tracked per model since most vendors only support a subset
- **37 pre-scored use cases**, mostly insurance-specific: claims, underwriting, pricing, life & health, reinsurance, distribution, document processing (OCR/PDF/invoice), and voice/video/image-generation scenarios
- A scoring engine that ranks all 25 models against any use case on complexity, latency sensitivity, volume/cost, context needs, regulatory exposure, and modality requirements

Every figure is sourced from vendor API pricing pages or Artificial Analysis's Intelligence Index, current as of June 2026. Treat it as a snapshot, not a permanent ranking — pricing and benchmarks change.

## Setup

Requires Python 3.9 or newer. No installation needed.

1. Save `model_advisor.py` to a folder on your computer.
2. Open a terminal:
   - **Mac**: Terminal app
   - **Windows**: Command Prompt or PowerShell
   - **Linux**: your terminal
3. Navigate to that folder:
   ```bash
   cd path/to/that/folder
   ```
4. Confirm Python works:
   ```bash
   python3 --version
   ```
   On Windows, try `python --version` if `python3` doesn't work — use whichever responds for the commands below.

If Python isn't installed, get it from [python.org/downloads](https://www.python.org/downloads/) (on Windows, check "Add Python to PATH" during setup).

## Usage

### Interactive chat mode
```bash
python3 model_advisor.py
```
Type a use case at the `Use case >` prompt and press Enter:
```
Use case > FNOL triage
Use case > summarize a 200-page commercial submission
Use case > quit
```

### One-shot mode
```bash
python3 model_advisor.py "FNOL triage"
```

## PTU vs. pay-as-you-go (Azure Provisioned Throughput)

Azure OpenAI offers two billing modes: **pay-as-you-go (PAYG)**, billed per token, and **Provisioned Throughput Units (PTU)**, reserved capacity billed hourly regardless of usage. Whether PTU is cheaper depends entirely on your volume and how much of that reserved capacity you actually use — there's no fixed answer, so the tool computes it from your numbers.

There are three ways to run this comparison. Pick whichever is easiest:

### Option A — guided wizard (easiest, no flags to remember)
Start the tool normally and type `ptu` at the prompt:
```bash
python3 model_advisor.py
```
```
Use case > ptu
```
It then asks for each value one at a time, showing a default in brackets — press Enter to accept the default, or type your own number:
```
Model (name or partial match): GPT-5.4
Number of PTUs you have or are pricing out: 10

Billing commitment affects the default $/PTU/hour:
  1) hourly                ~$3.35/PTU/hr
  2) monthly reservation   ~$2.02/PTU/hr
  3) annual reservation    ~$1.31/PTU/hr
Choose 1-3 [1]: 1
$ per PTU per hour [3.35]:
Tokens/minute per PTU for GPT-5.4 (planning default shown) [2500]:
Output-token capacity weight (derived from price ratio, shown as default) [6.0]:
Expected monthly INPUT tokens: 60000000
Expected monthly OUTPUT tokens: 40000000
```

### Option B — one-line command (fastest, good for scripting)
```bash
python3 model_advisor.py --ptu-model "GPT-5.4" --ptus 10 --monthly-tokens "60000000:40000000"
```
`--monthly-tokens` takes `INPUT:OUTPUT` token counts for one month (no spaces around the colon).

**Or, if you know your document volumes instead of raw token counts:**
```bash
python3 model_advisor.py \
  --compare-models "GPT-4.1,GPT-5.4" \
  --ptus 50 \
  --submissions 8000 \
  --forms-per-submission 30 \
  --pages-per-form 5 \
  --tokens-per-page 800 \
  --io-ratio 1.0
```
This derives the monthly token volume from your document stats, prints the full step-by-step derivation, then runs the PTU vs. PAYG comparison for every model listed.

### Option C — web app (no terminal at all)
Open `model_advisor_webapp.html` in any browser → scroll to Section 04, "Is reserved capacity worth it?" → pick a model and fill in the same fields as a form. Updates live as you type.

### What you get back
All three options produce the same result. For the example above:
```
------------------------------------------------------------------------
PTU vs. PAY-AS-YOU-GO — GPT-5.4
------------------------------------------------------------------------
  Monthly volume: 60,000,000 input + 40,000,000 output tokens
  PTU config: 10 PTUs @ $3.35/PTU/hr, 2,500 TPM/PTU (planning default — verify with Azure capacity calculator)
  Output-token capacity weight: 6.00x (derived from output:input price ratio — approximation)

  Required throughput:  6,849 TPM
  Your PTU capacity:    25,000 TPM
  -> Your PTUs COVER this volume, at 27.4% utilization.

  PTU monthly cost:   $24,455.00  (fixed, regardless of usage)
  PAYG monthly cost:  $750.00  (for this exact volume)
  -> PAYG is cheaper by $23,705.00/month (96.9%) at this volume.
```
Read top to bottom, it tells you: (1) whether your PTU count can actually handle the volume, and at what utilization, and (2) which billing mode is cheaper for that volume, and by how much.

### Overriding the defaults
Every PTU-specific number is configurable — Azure doesn't publish one universal figure for any of them, so don't trust the defaults blindly once you have a real quote:
```bash
python3 model_advisor.py --ptu-model "Claude Opus 4.7" --ptus 5 \
  --ptu-cost 2.50 --tpm-per-ptu 1500 --output-weight 5 \
  --monthly-tokens "20000000:15000000"
```
| Flag | What it sets | Default if omitted |
|---|---|---|
| `--ptu-model` | Which model to compare (name or partial match) | *(required for single-model)* |
| `--compare-models` | Comma-separated models for side-by-side comparison | *(optional)* |
| `--ptus` | PTUs you have or are pricing out | *(required)* |
| `--monthly-tokens` | Expected volume, `INPUT:OUTPUT` | *(required unless using --submissions)* |
| `--submissions` | Submissions/cases/files per year (alternative to --monthly-tokens) | — |
| `--forms-per-submission` | Average documents per submission | 1 |
| `--pages-per-form` | Average pages per document | 5 |
| `--tokens-per-page` | Estimated tokens per page (800 = dense insurance form) | 800 |
| `--io-ratio` | Output:input token ratio (0.2 = extraction; 1.0 = equal in/out) | 1.0 |
| `--ptu-cost` | $ per PTU per hour | industry-reported rate for `--ptu-billing` |
| `--ptu-billing` | `hourly` / `monthly_reservation` / `annual_reservation` | `hourly` (~$3.35/hr) |
| `--tpm-per-ptu` | Tokens/minute one PTU delivers for this model | a rough per-model planning estimate |
| `--output-weight` | Input-token-equivalents one output token consumes | derived from the model's output:input price ratio |

In every output, anything you set yourself is labeled "(your value)"; anything left as a default is labeled "(planning default — verify with Azure capacity calculator)" — so you always know which numbers came from you and which are estimates.

### Reference commands
```bash
python3 model_advisor.py --list              # all known use cases, by category
python3 model_advisor.py --models             # full model comparison table
python3 model_advisor.py --explain "Claude Sonnet 4.6"   # full reasoning for one model
python3 model_advisor.py "ACORD invoice OCR" --explain   # recommendation + full reasoning for the winner
python3 model_advisor.py "FNOL triage" --top 3            # show top 3 instead of top 5
```

The same shortcuts work as typed commands inside chat mode (`list`, `models`, `explain <model name>`, `<use case> +explain`, `help`, `quit`).

## How the recommendation is scored

For any use case, every model is scored on:

1. **Complexity → Intelligence target** — under-provisioning quality is penalized harder than over-provisioning, since getting it wrong costs more than paying for headroom.
2. **Latency → speed and time-to-first-token** — a baseline penalty for slow TTFT applies at every latency level (not just real-time use cases), since an outlier-slow first response is a real cost even for batch-tolerant work.
3. **Volume → cost weighting** — high-volume use cases weight price more heavily.
4. **Context → hard filter** — a model whose context window can't fit the document is excluded, not just penalized.
5. **Regulated workflows → soft penalty** for non-reasoning or unproven models on high-stakes tasks.
6. **Vision/OCR → hard filter plus accuracy bonus** — measured document accuracy (where published) outweighs raw cost, since a misread field costs more than the tokens saved.
7. **Open weights → hard filter** if self-hosting or data residency is required.
8. **Audio / video / image generation → hard filters** — these are real capability gaps held by only a few models, not a quality spectrum.

Run `--explain` on any model to see the specific justification behind every one of its numbers, not just the number itself.

## Known limitations

- Recommendations are a starting hypothesis from published benchmarks, not a controlled internal evaluation — validate against your own documents before committing to a vendor.
- A few figures (knowledge cutoffs for DeepSeek, Mistral, Qwen, Grok; eval cost for several models) aren't independently published by those vendors and are marked accordingly rather than estimated.
- Free-text queries that don't match a known use case fall back to a keyword-based heuristic guess — check the printed profile (`complexity`, `latency`, etc.) to make sure it read your request correctly, or use `--list` to find the closest pre-built match.
- PTU $/hour, tokens-per-minute-per-PTU, and the output-token capacity weight are not published by Azure as universal constants — the defaults shown are rough planning estimates, not quotes. Verify with Azure's own capacity calculator and your account team before committing budget to a PTU reservation.

## Companion materials

This tool shares its model database and scoring logic with:
- **Cross_Vendor_Model_Comparison_Insurance_Recommendations.pptx** — the full slide deck, including a per-use-case Model-to-Use-Case Map
- **Model_Parameter_Reference_Justified.docx** — a 34-page document with the full parameter table and per-model justification for every value
- **model_advisor_webapp.html** — a self-contained browser version with the same recommendation engine and PTU calculator as an interactive form (no install — just open the file)
