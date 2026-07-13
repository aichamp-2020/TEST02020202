#!/usr/bin/env python3
"""Streamlit UI for Model Advisor.

Run with: streamlit run model_advisor_streamlit.py
The calculation engine remains in model_advisor.py so CLI and UI agree.
"""
from __future__ import annotations

import csv
import html
import io
import re
from dataclasses import replace

import streamlit as st

from model_advisor import (
    CONTEXT_FLOOR_BY_LEVEL, DEFAULT_TPM_PER_PTU_FALLBACK, MODELS,
    PARAM_FALLBACK_JUSTIFICATIONS, PTUConfig, PTU_COST_DEFAULTS,
    TPM_PER_PTU_DEFAULTS, USE_CASES, UseCase, compare_ptu_vs_payg,
    estimate_monthly_tokens, find_use_case, guess_use_case_from_description, is_slm,
    payg_is_verified, payg_monthly_cost, rank_models,
)

st.set_page_config(page_title="Model Advisor", page_icon="⚖️", layout="wide")
st.markdown("""
<style>
:root{--navy:#12193f;--red:#b7432d;--ice:#eaf4f7}
.stApp{background:#ffffff;color:#1c2333}
.stApp p,.stApp label,.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp span{color:#1c2333}
.hero{background:var(--navy);color:#fff!important;padding:1.6rem 2rem;border-radius:0 0 18px 18px;margin-bottom:1rem}
.stApp div.hero h1,
.stApp div.hero h1 *{
  font-family:Georgia,serif;
  font-size:3rem;
  margin:0;
  color:#cdd2dc!important;
  -webkit-text-fill-color:#cdd2dc!important;
  opacity:1!important;
  text-shadow:0 1px 2px rgba(0,0,0,.25)
}
.stApp .hero p{color:#e7efff!important}
div[data-testid="stMetric"]{border:1px solid #d7dce6;border-radius:12px;padding:12px;background:white}
.stApp div[data-testid="stMetric"] label,.stApp div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:#1c2333}
.stApp div[data-baseweb="input"],.stApp div[data-baseweb="select"],.stApp div[data-baseweb="textarea"]{background:#fff;color:#1c2333}
.stApp div[data-baseweb="input"] input,.stApp div[data-baseweb="textarea"] textarea{color:#1c2333!important;-webkit-text-fill-color:#1c2333!important;caret-color:#1c2333}
.stApp div[data-baseweb="select"]>div{background:#fff;color:#1c2333;border-color:#8a93a6}
.stApp div[data-baseweb="select"] span,.stApp div[data-baseweb="select"] svg{color:#1c2333;fill:#1c2333}
.stApp [data-testid="stWidgetLabel"] p,.stApp [data-testid="stMarkdownContainer"]{color:#1c2333}
.stApp button[data-baseweb="tab"] p,.stApp button[data-baseweb="tab"]{color:#1c2333}
div[data-baseweb="popover"],div[data-baseweb="menu"],ul[role="listbox"]{background:#fff!important;color:#1c2333!important}
div[data-baseweb="popover"] li,div[data-baseweb="menu"] li,li[role="option"]{background:#fff!important;color:#1c2333!important}
div[data-baseweb="popover"] li:hover,div[data-baseweb="menu"] li:hover,li[role="option"]:hover{background:#eaf4f7!important}
li[role="option"] span{color:#1c2333!important}
.note{background:#dff1f5;padding:14px 18px;border-radius:6px}.warn{background:#fff0c7;padding:14px 18px;border-radius:6px}
.small{font-size:.84rem;color:#5b6472}
.result-table-wrap{overflow-x:auto;margin:12px 0 22px;border:1px solid #d7dce6;border-radius:10px}
.result-table{width:100%;border-collapse:collapse;font-size:.86rem;background:#fff;color:#1c2333}
.result-table th{background:#12193f;color:#fff!important;text-align:left;padding:9px 11px;white-space:nowrap;cursor:help;text-decoration:underline dotted;text-underline-offset:3px}
.result-table td{padding:8px 11px;border-bottom:1px solid #e2e6ee;white-space:nowrap;color:#1c2333!important}
.result-table tr:nth-child(even) td{background:#f3f6fd}
.score-row{display:grid;grid-template-columns:minmax(190px,1.4fr) 5fr 70px;gap:12px;align-items:center;margin:9px 0;color:#1c2333}
.score-track{height:14px;background:#e2e6ee;border-radius:999px;overflow:hidden}.score-fill{height:100%;background:linear-gradient(90deg,#2e3a8c,#b7432d);border-radius:999px}
.score-name,.score-value{color:#1c2333!important;font-weight:600}.score-value{text-align:right}
</style>
<div class="hero"><h1 style="color:#cdd2dc!important;-webkit-text-fill-color:#cdd2dc!important;opacity:1!important;">Model Advisor</h1><p>One recommendation engine, one PTU calculator, and a business decision cockpit.</p></div>
""", unsafe_allow_html=True)


def model_display(model):
    return f"{model.name} (SLM)" if is_slm(model) else model.name


def model_rows(models=MODELS):
    return [{"Model":model_display(m),"Vendor":m.vendor,"Released":m.release_date,"In $/M":m.input_price,"Out $/M":m.output_price,
             "Blend $/M":round(m.blended_price(),3),"Context":m.context,"Intel":m.intelligence,
             "tok/s":m.speed,"TTFT s":m.ttft,"Open":m.open_weight,"Vision":m.vision,
             "Audio":m.audio_input,"Video":m.video_input,"Image gen":m.image_gen,
             "PAYG Verified":payg_is_verified(m),"SLM":is_slm(m)} for m in models]


METRIC_HELP={
    "Complexity":"Use-case reasoning difficulty from 1 (simple extraction/lookup) to 5 (deep expert reasoning). It sets the target Intelligence Index.",
    "Latency":"Response-time sensitivity from 1 (batch) to 5 (real time). Higher values increase speed and TTFT importance.",
    "Volume":"Expected workload scale from 1 to 5. Higher volume increases the scoring penalty for expensive token prices.",
    "Context":"Required context tier from 1 (<8K) to 5 (2M+). Models below the required context receive a hard penalty.",
    "Intelligence":"Artificial Analysis Intelligence Index where available. It is a comparative benchmark, not a guarantee for this specific task.",
    "Required TPM":"Weighted input-token-equivalent throughput required per minute across 730 operating hours/month.",
    "Available TPM":"Number of PTUs multiplied by the model-specific planning estimate for TPM delivered per PTU.",
    "PTUs needed":"Required TPM divided by estimated TPM per PTU. Procurement may require rounding and minimum deployment sizes.",
    "Utilization":"Required TPM divided by available TPM. Low utilization usually makes fixed PTU capacity uneconomical.",
    "Capacity headroom":"Available TPM minus required TPM. A negative value means the selected capacity cannot serve the workload.",
    "Minimum PTUs":"Calculated fractional PTUs required for average monthly throughput; validate peak/burst needs separately.",
    "PAYG monthly cost":"Usage-based cost: input tokens ÷ 1M × model input price, plus output tokens ÷ 1M × model output price. It excludes taxes, network charges, discounts and ancillary Azure services.",
    "PTU monthly cost":"Fixed reserved-capacity cost: total annual PTU contract cost ÷ 12. You pay this amount regardless of actual utilization; it excludes taxes and organization-specific Azure discounts unless included in the entered contract total.",
    "Monthly difference":"Absolute difference between PTU monthly cost and PAYG monthly cost. The UI separately identifies which option is cheaper; a positive displayed difference is the potential monthly savings from choosing that cheaper viable option.",
    "Assumed monthly input":"Estimated monthly input volume derived from document count × pages per document × approximately 850 input tokens per page. The quick view assumes the stated batch runs once per month.",
    "PAYG / month":"Estimated usage-based monthly cost for the recommended model: input-token cost plus output-token cost at current list prices.",
    "50-PTU contract / month":"Fixed monthly equivalent of the default 50-PTU, $162,000 annual contract: annual cost ÷ 12. It is paid regardless of utilization.",
    "Recommendation":"Quick billing verdict. PTU is selected only when its capacity covers the workload and its monthly cost is lower; otherwise PAYG is selected.",
    "Weighted score":"Composite 0–100 business score using the adjustable quality, economics, latency and risk weights.",
    "Final recommendation":"PTU wins only when it is cheaper and capacity is sufficient; otherwise PAYG wins.",
}

TABLE_COLUMN_HELP={
    "Model":"Model name. “SLM” identifies a small-language-model tier suitable for lower-cost or self-hosted workloads.",
    "Vendor":"Organization that develops or publishes the model.",
    "Score":"Relative use-case fit calculated from intelligence, latency, volume cost, context, governance and required capabilities. Higher is better.",
    "Intel":"Artificial Analysis Intelligence Index score where independently measured. Higher is better; reasoning effort can affect the score.",
    "In $/M":"List price in US dollars per one million uncached input tokens.",
    "Out $/M":"List price in US dollars per one million generated output tokens.",
    "Context":"Maximum combined context window in tokens. The usable input limit can be lower after reserving output tokens.",
    "tok/s":"Approximate generated output tokens per second after generation begins. Higher is faster.",
    "TTFT s":"Approximate time to first token in seconds. Lower generally feels more responsive; reasoning effort can increase it substantially.",
    "Vision":"Whether the model accepts image or scanned-document input.",
    "Open":"Whether downloadable model weights are available for self-hosting, subject to the applicable license.",
    "Active Rank":"Rank for the workload entered in tab 01. A dash means the model falls outside the selected Top-N range.",
    "PAYG Verified":"True only when a first-party or specifically named managed usage-based API was verified for this exact model line. False means token cost is an estimate or self-deployment/third-party hosting is required.",
    "Price/image":"Published starting PAYG price for the stated default quality/resolution. Editing, higher resolution and image-token inputs can cost more.",
    "Image score":"Relative fit using image quality, speed, text rendering, editing requirements and workload-volume cost. Higher is better.",
    "Monthly image cost":"Image count multiplied by starting price per image; excludes text-model tokens, editing premiums, upscaling, taxes and discounts.",
}

IMAGE_MODELS=[
    {"name":"Nano Banana Pro","vendor":"Google","price":0.134,"quality":96,"speed":65,"text":98,"editing":True,"resolution":"1K/2K","payg":True,"note":"Premium instruction following, brand consistency and text rendering; 4K costs about $0.24/image."},
    {"name":"Imagen 4 Ultra","vendor":"Google Vertex AI","price":0.06,"quality":94,"speed":55,"text":84,"editing":False,"resolution":"High resolution","payg":True,"note":"Premium photorealism; Imagen retirement is announced for August 17, 2026, so plan migration."},
    {"name":"Imagen 4 Fast","vendor":"Google Vertex AI","price":0.02,"quality":78,"speed":92,"text":70,"editing":False,"resolution":"Standard","payg":True,"note":"Low-cost, high-throughput image generation; Imagen retirement is announced for August 17, 2026."},
    {"name":"FLUX.2 [klein] 4B","vendor":"Black Forest Labs","price":0.014,"quality":74,"speed":96,"text":72,"editing":True,"resolution":"From 1 MP","payg":True,"note":"Lowest-cost real-time/high-volume FLUX tier; price increases with megapixels."},
    {"name":"FLUX.2 [pro]","vendor":"Black Forest Labs","price":0.03,"quality":88,"speed":84,"text":86,"editing":True,"resolution":"MP-based","payg":True,"note":"Balanced production image generation; editing starts around $0.045/image."},
    {"name":"FLUX.2 [max]","vendor":"Black Forest Labs","price":0.07,"quality":97,"speed":52,"text":91,"editing":True,"resolution":"MP-based","payg":True,"note":"Highest-quality FLUX tier with grounding; cost scales with output resolution."},
]


def rank_image_models(description, image_count):
    q=description.lower(); high_volume=image_count>=10_000
    needs_text=any(word in q for word in ("text","typography","poster","label","slide","education","edtech"))
    needs_edit=any(word in q for word in ("edit","reference","consistent","brand","modify"))
    rows=[]
    for model in IMAGE_MODELS:
        score=model["quality"]*.55+model["speed"]*.15+model["text"]*(.25 if needs_text else .10)
        if needs_edit and not model["editing"]: score-=20
        score-=model["price"]*(180 if high_volume else 60)
        rows.append({**model,"score":round(score,1),"monthly_cost":round(image_count*model["price"],2)})
    return sorted(rows,key=lambda row:row["score"],reverse=True)


def show_metrics(items):
    cols=st.columns(len(items))
    for col,item in zip(cols,items):
        label,value=item[:2]
        item_help=item[2] if len(item)>2 else METRIC_HELP.get(label)
        col.metric(label,value,help=item_help)


def render_result_table(rows, columns=None):
    """Render variable-length rankings without Streamlit/PyArrow dataframe rerun crashes."""
    columns=columns or (["Model","Vendor","Score","Intel","In $/M","Out $/M","Context","tok/s","TTFT s","Vision","Open"] if rows else [])
    head="".join(f'<th title="{html.escape(TABLE_COLUMN_HELP.get(c,""),quote=True)}">{html.escape(c)}</th>' for c in columns)
    body="".join("<tr>"+"".join(f"<td>{html.escape(str(row.get(c,'—')))}</td>" for c in columns)+"</tr>" for row in rows)
    st.markdown(f'<div class="result-table-wrap"><table class="result-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>',unsafe_allow_html=True)


def render_weighted_scores(rows):
    bars="".join(
        f'<div class="score-row"><div class="score-name">{html.escape(str(row["Model"]))}</div>'
        f'<div class="score-track"><div class="score-fill" style="width:{max(0,min(100,float(row["Weighted Score"]))):.1f}%"></div></div>'
        f'<div class="score-value">{float(row["Weighted Score"]):.1f}</div></div>' for row in rows)
    st.markdown(bars,unsafe_allow_html=True)


def render_ptu_decision_summary(result, model, cfg, monthly_in, monthly_out, label="How this decision was calculated"):
    """Show an auditable explanation of the PTU/PAYG cost and capacity verdict."""
    annual_contract=result["ptu_monthly_cost"]*12
    out_weight=result["output_weight_used"]
    weighted_tokens=monthly_in+(monthly_out*out_weight)
    minutes=cfg.hours_per_month*60
    cost_break_even=(result["ptu_monthly_cost"]/result["payg_monthly_cost"]) if result["payg_monthly_cost"] else None
    viable_ptu=result["covers_volume"] and result["ptu_monthly_cost"] < result["payg_monthly_cost"]
    utilization=f"{result['utilization_pct']:.1f}%" if result["utilization_pct"] is not None else "not available (zero capacity)"
    capacity_headroom=result["available_tpm"]-result["required_tpm"]
    cost_delta=result["ptu_monthly_cost"]-result["payg_monthly_cost"]
    break_even_in=monthly_in*cost_break_even if cost_break_even else None
    break_even_out=monthly_out*cost_break_even if cost_break_even else None
    exact_capacity_cost=result["ptus_needed"]*cfg.ptu_hourly_cost*cfg.hours_per_month
    with st.expander(label,expanded=True):
        show_metrics([
            ("Final recommendation","PTU" if viable_ptu else "PAYG"),
            ("Monthly difference",f"${abs(cost_delta):,.2f}"),
            ("Capacity headroom",f"{capacity_headroom:,.0f} TPM"),
            ("Minimum PTUs",f"{result['ptus_needed']:.1f}"),
        ])
        st.markdown(f"""
### Inputs used

- Model: **{model.name}**
- Monthly volume: **{monthly_in:,.0f} input tokens** and **{monthly_out:,.0f} output tokens**
- Model prices: **${model.input_price:g}/M input**, **${model.output_price:g}/M output**
- Contract: **{cfg.ptus_available:g} PTUs**, **${annual_contract:,.2f}/year**, **{cfg.hours_per_month:g} hours/month**
- Capacity assumption: **{result['tpm_per_ptu_used']:,.0f} TPM per PTU**; output capacity weight: **{out_weight:.2f}×**

**1. PAYG token cost**

- Input: `{monthly_in:,.0f} ÷ 1,000,000 × ${model.input_price:g}` = **${monthly_in/1_000_000*model.input_price:,.2f}/month**
- Output: `{monthly_out:,.0f} ÷ 1,000,000 × ${model.output_price:g}` = **${monthly_out/1_000_000*model.output_price:,.2f}/month**
- Total PAYG = **${result['payg_monthly_cost']:,.2f}/month** or **${result['payg_monthly_cost']*12:,.2f}/year**

**2. PTU contract cost**

- Annual contract represented by the current inputs: **${annual_contract:,.2f}/year**
- Monthly PTU cost: `${annual_contract:,.2f} ÷ 12` = **${result['ptu_monthly_cost']:,.2f}/month**
- Effective hourly rate: `${annual_contract:,.2f} ÷ ({cfg.ptus_available:g} PTUs × 730 hours × 12 months)` = **${cfg.ptu_hourly_cost:,.4f}/PTU/hour**
- Estimated cost of exactly the required **{result['ptus_needed']:.1f} PTUs** at the same rate = **${exact_capacity_cost:,.2f}/month**. Actual Azure purchases may require whole PTU increments and minimum deployment sizes.

**3. Capacity check**

- Output tokens consume approximately **{out_weight:.2f}×** input-token capacity for this model.
- Weighted monthly tokens: `{monthly_in:,.0f} + ({monthly_out:,.0f} × {out_weight:.2f})` = **{weighted_tokens:,.0f}**
- Required TPM: `{weighted_tokens:,.0f} ÷ {minutes:,.0f} minutes` = **{result['required_tpm']:,.0f} TPM**
- Available TPM: `{cfg.ptus_available:g} PTUs × {result['tpm_per_ptu_used']:,.0f} TPM/PTU` = **{result['available_tpm']:,.0f} TPM**
- Utilization: **{utilization}**; PTUs required: **{result['ptus_needed']:.1f}**; capacity covers workload: **{'Yes' if result['covers_volume'] else 'No'}**
- Capacity headroom: `{result['available_tpm']:,.0f} − {result['required_tpm']:,.0f}` = **{capacity_headroom:,.0f} TPM** {'available' if capacity_headroom >= 0 else 'shortfall'}

**4. Cost comparison**

- PAYG annual run cost: **${result['payg_monthly_cost']*12:,.2f}**
- PTU annual contract cost: **${annual_contract:,.2f}**
- Difference: **${abs(cost_delta):,.2f}/month** or **${abs(cost_delta)*12:,.2f}/year** in favor of **{'PTU' if cost_delta < 0 and result['covers_volume'] else 'PAYG'}**

**5. Decision rule and explanation**

PTU is recommended only when **both** conditions are true: (a) PTU capacity covers the workload and (b) PTU monthly cost is lower than PAYG. For the current inputs, the recommendation is **{'PTU' if viable_ptu else 'PAYG'}**.
""")
        if cost_break_even:
            st.markdown(f"""
**6. Break-even traffic**

- Cost-only multiplier: `${result['ptu_monthly_cost']:,.2f} ÷ ${result['payg_monthly_cost']:,.2f}` = **{cost_break_even:.2f}× current traffic**
- At the same token mix, PAYG reaches the PTU contract cost at approximately **{break_even_in:,.0f} input** and **{break_even_out:,.0f} output tokens/month**.
- This is a cost break-even only. PTU capacity must be recalculated at that volume; cost break-even does not guarantee that {cfg.ptus_available:g} PTUs can serve it.
""")
        if viable_ptu:
            st.success(f"Why PTU won: the contract is ${abs(cost_delta):,.2f}/month cheaper than PAYG and provides {capacity_headroom:,.0f} TPM of capacity headroom.")
        elif not result["covers_volume"]:
            st.warning(f"Why PAYG won: the selected PTUs are short by {abs(capacity_headroom):,.0f} TPM. A lower nominal PTU price cannot be recommended when the deployment cannot serve the workload.")
        else:
            st.info(f"Why PAYG won: capacity is sufficient, but the PTU contract costs ${abs(cost_delta):,.2f}/month more than usage-based billing at the current workload.")
        st.caption("Planning assumptions: 730 operating hours/month; model-specific TPM/PTU and output-capacity weight are estimates unless overridden. Verify region, model availability, quota, deployment minimums, burst behavior and quoted Azure capacity before procurement.")


def document_profile(base: UseCase, count, pages, scanned, task, latency, regulated, open_weight):
    context = 5 if pages >= 150 else 4 if pages >= 40 else 3 if pages >= 8 else base.context
    volume = 5 if count*pages >= 1_000_000 else 4 if count*pages >= 75_000 else 3 if count*pages >= 10_000 else base.volume
    latency_score={"Batch / overnight":1,"Minutes":2,"Interactive":4,"Real-time":5}[latency]
    return replace(base, context=context, volume=volume, latency=latency_score,
                   regulated=regulated, open_weight=open_weight,
                   vision=base.vision or scanned>0 or task=="OCR field extraction")


def parse_workload(text):
    """Extract common document-workload quantities from plain English."""
    clean=text.lower().replace(",","")
    count_match=re.search(r"(\d+(?:\.\d+)?)\s*(k|m)?\s*(?:pdfs?|documents?|docs?|files?|forms?)",clean)
    pages_match=re.search(r"(\d+(?:\.\d+)?)\s*pages?\s*(?:each|per\s*(?:pdf|document|doc|file|form))?",clean)
    multiplier={"k":1_000,"m":1_000_000,"b":1_000_000_000,None:1}
    count=int(float(count_match.group(1))*multiplier[count_match.group(2)]) if count_match else None
    pages=float(pages_match.group(1)) if pages_match else None
    document_words=any(word in clean for word in ("pdf","document","doc","page","ocr","form","invoice"))
    if "ocr" in clean or "invoice" in clean or "acord" in clean:
        inferred=find_use_case("ACORD invoice OCR")
    elif document_words:
        inferred=find_use_case("Policy document digitization")
    else:
        inferred=find_use_case(text)
    def token_value(kind):
        patterns=[
            rf"(\d+(?:\.\d+)?)\s*([kmb])?\s*{kind}(?:\s*tokens?)?",
            rf"{kind}(?:\s*tokens?)?\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*([kmb])?",
        ]
        for pattern in patterns:
            match=re.search(pattern,clean)
            if match: return float(match.group(1))*multiplier[match.group(2)]
        return None
    input_tokens=token_value("input")
    output_tokens=token_value("output")
    # Normalize explicit traffic to a monthly basis.
    if any(term in clean for term in ("per day","/day","daily","each day","a day")): frequency=365/12
    elif any(term in clean for term in ("per year","/year","yearly","annual","each year","a year")): frequency=1/12
    elif any(term in clean for term in ("per week","/week","weekly","each week","a week")): frequency=52/12
    else: frequency=1  # monthly, per month, /month, each month, or no frequency supplied
    input_tokens=input_tokens*frequency if input_tokens is not None else None
    output_tokens=output_tokens*frequency if output_tokens is not None else None
    return count,pages,inferred,input_tokens,output_tokens


def ptu_inputs(prefix, default_model, default_in=60_000_000.0, default_out=40_000_000.0,
               default_ptus=10.0, default_pricing="Planning default",
               annual_contract_default=None, simple_annual=False,
               shared_ptus=None, shared_annual_cost=None):
    model_key=prefix+"model"
    model_kwargs={} if model_key in st.session_state else {"index":MODELS.index(default_model)}
    model=st.selectbox("Model",MODELS,format_func=model_display,key=model_key,**model_kwargs)
    if simple_annual:
        ptus=float(shared_ptus if shared_ptus is not None else default_ptus)
        annual_total=float(shared_annual_cost if shared_annual_cost is not None else annual_contract_default or 0)
        show_metrics([("Number of PTUs",f"{ptus:g}","Shared parameter; change it in the sidebar."),("Total PTU cost per year",f"${annual_total:,.2f}","Shared parameter; change it in the sidebar.")])
        with st.expander("Monthly token volume and capacity overrides (optional)"):
            a,b=st.columns(2)
            in_key=prefix+"in"; out_key=prefix+"out"
            in_kwargs={} if in_key in st.session_state else {"value":float(default_in)}
            out_kwargs={} if out_key in st.session_state else {"value":float(default_out)}
            monthly_in=a.number_input("Monthly input tokens",0.0,step=1_000_000.0,key=in_key,**in_kwargs)
            monthly_out=b.number_input("Monthly output tokens",0.0,step=1_000_000.0,key=out_key,**out_kwargs)
            a,b=st.columns(2)
            tpm=a.number_input("Tokens/min per PTU (0 = model default)",0.0,value=0.0,key=prefix+"tpm")
            weight=b.number_input("Output-token capacity weight (0 = model default)",0.0,value=0.0,key=prefix+"weight")
        hourly_rate=annual_total/(max(ptus,1)*730*12)
        return model,monthly_in,monthly_out,PTUConfig(
            ptus,hourly_rate,tpm_per_ptu=tpm or None,output_weight=weight or None)

    pricing_options=["Planning default","Annual contract total","Monthly contract total","Exact hourly rate"]
    pricing=st.radio("How do you want to set PTU hourly cost?", pricing_options,
                     index=pricing_options.index(default_pricing), key=prefix+"method")
    billing=st.selectbox("Billing profile", list(PTU_COST_DEFAULTS), format_func=lambda x:x.replace("_"," ").title(), key=prefix+"billing")
    c1,c2,c3=st.columns(3)
    ptus=c1.number_input("PTUs available / priced",0.0,value=default_ptus,key=prefix+"ptus",
                         help="Enter the PTU quantity in your quote, for example 50.")
    monthly_in=c2.number_input("Monthly input tokens",0.0,value=float(default_in),step=1_000_000.0,key=prefix+"in")
    monthly_out=c3.number_input("Monthly output tokens",0.0,value=float(default_out),step=1_000_000.0,key=prefix+"out")
    default_rate=PTU_COST_DEFAULTS[billing]
    if pricing=="Annual contract total":
        annual_default=annual_contract_default if annual_contract_default is not None else ptus*default_rate*730*12
        annual_total=st.number_input("Annual PTU contract total ($)",0.0,value=float(annual_default),
                                     placeholder="e.g. 162000",key=prefix+"annual",
                                     help="Enter the total annual price for all PTUs, not the price per PTU.")
        rate=annual_total/(max(ptus,1)*730*12)
    elif pricing=="Monthly contract total": rate=st.number_input("Monthly contract total ($)",0.0,value=ptus*default_rate*730,key=prefix+"monthly")/(max(ptus,1)*730)
    elif pricing=="Exact hourly rate": rate=st.number_input("$ per PTU/hour",0.0,value=default_rate,key=prefix+"rate")
    else: rate=default_rate
    with st.expander("Advanced overrides (optional)"):
        a,b=st.columns(2)
        tpm=a.number_input("Tokens/min per PTU (0 = model default)",0.0,value=0.0,key=prefix+"tpm")
        weight=b.number_input("Output-token capacity weight (0 = price-ratio default)",0.0,value=0.0,key=prefix+"weight")
    cfg=PTUConfig(ptus,rate,tpm_per_ptu=tpm or None,output_weight=weight or None)
    return model,monthly_in,monthly_out,cfg


with st.sidebar:
    st.header("Shared PTU assumptions")
    shared_ptus=st.number_input("Number of PTUs",min_value=0.0,value=50.0,step=1.0,key="shared_ptus",help="Applied to quick recommendation, PTU/PAYG and Decision Cockpit.")
    shared_annual_cost=st.number_input("Total PTU cost per year ($)",min_value=0.0,value=162_000.0,step=1_000.0,key="shared_annual_cost",help="Full annual contract price for all PTUs combined; applied across every tab.")
    st.caption("Changing either value automatically recalculates all PTU cost, capacity, utilization and break-even results.")

tabs=st.tabs(["01 Recommend","02 Model Table","03 Use Cases","04 Explain Model","05 PTU vs PAYG","06 Decision Cockpit"])

with tabs[0]:
    st.caption("01 · RECOMMENDATION"); st.header("Describe the use case")
    q=st.text_input("Use case or workload", "Process 8,000 PDFs with 5 pages each",
                    help="""Examples:

- Process 8,000 PDFs with 5 pages each
- Claims OCR with 34M input tokens and 3.4M output tokens per month
- 500K input tokens and 50K output tokens daily
- 10M input tokens per week
- 2B input tokens and 200M output tokens per year

Supports **K, M, B** and **daily, weekly, monthly, yearly** frequency.""")
    top_n=st.slider("Top N",3,20,5,help="Controls how many of the 31 scored models appear in the ranked recommendation table.")
    parsed_docs,parsed_pages,inferred_profile,parsed_input_tokens,parsed_output_tokens=parse_workload(q)
    known=inferred_profile or find_use_case(q) or guess_use_case_from_description(q)
    with st.expander("Pick from known use cases"):
        override_profile=st.checkbox("Override automatically inferred profile",False)
        if override_profile:
            known=st.selectbox("Known profile",USE_CASES,index=USE_CASES.index(known) if known in USE_CASES else 0,format_func=lambda x:f"{x.name} — {x.category}")
    clean_q=q.lower().replace(",","")
    is_document_workload=any(word in clean_q for word in ("pdf","document","doc","page","ocr","invoice","form"))
    users_match=re.search(r"(\d+(?:\.\d+)?)\s*([kmb])?\s*users?",clean_q)
    per_user_match=re.search(
        r"(\d+(?:\.\d+)?)\s*([kmb])?\s*(?:generations?|requests?|calls?|items?)\s*(?:per\s*user|each\s*user|for\s*each\s*user|per\s*each\s*user)",
        clean_q,
    )
    images_match=re.search(r"(\d+(?:\.\d+)?)\s*([kmb])?\s*images?",clean_q)
    scale={None:1,"k":1_000,"m":1_000_000,"b":1_000_000_000}
    users=int(float(users_match.group(1))*scale[users_match.group(2)]) if users_match else None
    per_user=int(float(per_user_match.group(1))*scale[per_user_match.group(2)]) if per_user_match else None
    requests=(users*per_user) if users is not None and per_user is not None else None
    explicit_images=int(float(images_match.group(1))*scale[images_match.group(2)]) if images_match else None
    if is_document_workload:
        st.subheader("PDF / DOC / OCR details")
        docs=parsed_docs or 10_000; pages=parsed_pages or 8.0
        c1,c2,c3=st.columns(3)
        c1.metric("PDFs/docs extracted",f"{docs:,}")
        c2.metric("Pages per document",f"{pages:g}")
        scanned=c3.slider("% scanned/image PDFs",0,100,50,help="Any scanned/image content requires a vision-capable model; OCR accuracy becomes a ranking factor.")
    else:
        st.subheader("General workload details")
        docs=0; pages=0.0; scanned=0
        show_metrics([("Users",f"{users:,}" if users is not None else "Not supplied","Users parsed from the chat workload."),("Generations per user",f"{per_user:,}" if per_user is not None else "Not supplied","Requests/generations per user parsed from chat."),("Total generations",f"{requests:,}" if requests is not None else "Estimated from tokens","Users × generations per user.")])
    c1,c2,c3=st.columns(3)
    task_options=["OCR field extraction","Summarization","Classification","Question answering"] if is_document_workload else ["Content generation","Question answering","Classification","Summarization"]
    task=c1.selectbox("Primary task",task_options,help="Changes capability requirements and the estimated output-token ratio used for cost calculations.")
    latency=c2.selectbox("Latency expectation",["Batch / overnight","Minutes","Interactive","Real-time"],help="Interactive/real-time workloads reward faster generation and lower time-to-first-token.")
    regulated=c3.checkbox("Regulated/compliance-sensitive",known.regulated,help="Adds governance guidance and favors reasoning/auditable models for higher-complexity work.")
    open_required=st.checkbox("Need open weights / self-hosting",known.open_weight,help="When enabled, proprietary models receive a hard scoring penalty because their weights cannot be self-hosted.")
    uc=document_profile(known,docs or 1,pages or 1,scanned,task,latency,regulated,open_required)
    if not is_document_workload:
        needs_image_generation="image" in clean_q and any(word in clean_q for word in ("generat","create","content"))
        uc=replace(uc,vision=False,image_gen=uc.image_gen or needs_image_generation)
    explicit_tokens=parsed_input_tokens is not None or parsed_output_tokens is not None
    derived_input=float(docs*pages*850) if is_document_workload else float((requests or 1_000)*500)
    workload_in=float(parsed_input_tokens if parsed_input_tokens is not None else derived_input)
    derived_output=workload_in*(0.10 if task=="OCR field extraction" else 0.50 if task=="Content generation" else 0.20)
    workload_out=float(parsed_output_tokens if parsed_output_tokens is not None else derived_output)
    token_volume=workload_in+workload_out
    volume_level=5 if token_volume>=500_000_000 else 4 if token_volume>=100_000_000 else 3 if token_volume>=20_000_000 else 2 if token_volume>=5_000_000 else 1
    if explicit_tokens: uc=replace(uc,volume=volume_level)
    if explicit_tokens:
        output_source="explicit" if parsed_output_tokens is not None else f"estimated from the {task.lower()} task"
        explicit_note=f"Token volume applied: {workload_in:,.0f} input and {workload_out:,.0f} output tokens/month ({output_source}). Explicit values override document-derived estimates."
        st.markdown(f'<div class="note">{explicit_note}</div>',unsafe_allow_html=True)
    else:
        if is_document_workload:
            st.markdown(f'<div class="note">Document profile applied: {docs:,} docs, ~{pages:g} pages/doc, {scanned}% scanned; estimated {docs*pages*850:,.0f} input tokens.</div>',unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="note">General workload profile applied: {requests or 1_000:,} monthly generations; estimated {workload_in:,.0f} input and {workload_out:,.0f} output tokens. Image-generation API charges are separate from text-token costs.</div>',unsafe_allow_html=True)
    show_metrics([("Complexity",f"{uc.complexity}/5"),("Latency",f"{uc.latency}/5"),("Volume",f"{uc.volume}/5"),("Context",f"{uc.context}/5"),("Flags","regulated" if uc.regulated else "standard")])
    ranked=rank_models(uc); winner=ranked[0][0]; runner=ranked[1][0]
    active_top_models=[model for model,_score in ranked[:top_n]]
    active_rank={model.name:index for index,(model,_score) in enumerate(ranked[:top_n],1)}
    with st.expander("How the recommendation score is calculated"):
        st.markdown("""
- **Intelligence fit:** compares model intelligence with the target for complexity; underpowered models receive an additional penalty.
- **Latency:** every model receives a TTFT penalty; latency-sensitive workloads add stronger speed rewards and TTFT penalties.
- **Volume economics:** high-volume workloads penalize input/output prices more heavily.
- **Context:** models below the required context tier receive a hard penalty; qualifying models receive limited headroom credit.
- **Governance:** regulated, complex work penalizes non-reasoning models and adds documented governance guidance.
- **Capability gates:** missing required vision, audio, video, image generation or open weights receives a hard penalty.
- **Document quality:** when vision is required, published OCR/document accuracy can improve the score.

The score is a relative ranking signal. Validate finalists on representative documents before production approval.
""")
    st.subheader("Recommended")
    winner_label=f"{winner.name} (SLM)" if is_slm(winner) else winner.name
    runner_label=f"{runner.name} (SLM)" if is_slm(runner) else runner.name
    show_metrics([("Model",winner_label),("Vendor",winner.vendor),("Intelligence",winner.intelligence or "—"),("Input price",f"${winner.input_price:.2f}/M"),("Output price",f"${winner.output_price:.2f}/M")])
    st.write(f"Runner-up: **{runner_label}** ({runner.vendor}). {winner.notes}")
    if uc.regulated: st.markdown('<div class="warn">Regulated workflow: log prompts, model version, inputs and outputs; maintain human review and a current model card.</div>',unsafe_allow_html=True)
    st.subheader(f"Top {top_n} ranked models")
    rows=[]
    for m,s in ranked[:top_n]: rows.append({**model_rows([m])[0],"Score":round(s,1)})
    render_result_table(rows)
    if uc.image_gen:
        image_count=explicit_images or requests or 1_000
        image_ranked=rank_image_models(q,image_count)
        image_winner=image_ranked[0]
        st.subheader("Dedicated image-model recommendation")
        show_metrics([("Image model",image_winner["name"],"Dedicated model recommended for generating the image output."),("Provider",image_winner["vendor"]),("Images / month",f"{image_count:,}","Uses an explicit image count when provided; otherwise assumes one image per generation/request."),("Price / image",f"${image_winner['price']:.3f}"),("Image cost / month",f"${image_winner['monthly_cost']:,.2f}")])
        st.write(image_winner["note"])
        image_rows=[{"Model":row["name"],"Vendor":row["vendor"],"Image score":row["score"],"Price/image":f"${row['price']:.3f}","Monthly image cost":f"${row['monthly_cost']:,.2f}","Resolution":row["resolution"],"Editing":row["editing"],"PAYG Verified":row["payg"]} for row in image_ranked]
        render_result_table(image_rows,list(image_rows[0]))
        st.warning("Image cost is calculated separately from LLM text-token cost. Add both amounts for the combined workload estimate. Published per-image rates vary by quality, resolution, editing and batch mode.")
    st.subheader("PTU vs. PAYG — quick recommendation")
    active_signature=(q,known.name,docs,pages,scanned,task,latency,regulated,open_required,winner.name,workload_in,workload_out,top_n)
    if st.session_state.get("active_workload_signature") != active_signature:
        # Synchronize downstream tabs only when the source workload/profile changes.
        # Manual PTU or cockpit edits survive ordinary widget reruns.
        st.session_state["active_workload_signature"]=active_signature
        st.session_state["explain"]=winner
        st.session_state["ptu_model"]=winner
        st.session_state["ptu_in"]=workload_in
        st.session_state["ptu_out"]=workload_out
        st.session_state["dcin"]=workload_in
        st.session_state["dcout"]=workload_out
        st.session_state["dcmodels"]=active_top_models
    st.caption("Live calculation: changing any workload, document, task, latency, compliance, model, token, PTU, annual-cost or weighting input automatically reruns the recommendation and all derived values.")
    quick_hourly=shared_annual_cost/(max(shared_ptus,1)*730*12)
    quick_cfg=PTUConfig(shared_ptus,quick_hourly)
    quick=compare_ptu_vs_payg(winner,quick_cfg,workload_in,workload_out)
    quick_payg_verified=payg_is_verified(winner)
    show_metrics([("Assumed monthly input",f"{workload_in/1_000_000:.1f}M"),
                  ("PAYG / month",f"${quick['payg_monthly_cost']:,.2f}"),
                  ("PTU contract / month",f"${quick['ptu_monthly_cost']:,.2f}",f"Shared contract: {shared_ptus:g} PTUs at ${shared_annual_cost:,.2f}/year."),
                  ("Recommendation",quick['cheaper_option'] if quick_payg_verified or quick['cheaper_option']!='PAYG' else "PAYG estimate — unverified")])
    if not quick_payg_verified:
        st.warning(f"PAYG availability is not verified for {winner.name}. The displayed token cost is a hosting estimate; do not treat it as an available first-party PAYG offer until a provider/region is confirmed.")
    if quick["cheaper_option"]=="PAYG":
        st.info(f"For this workload, use {winner.name} on PAYG. PAYG saves ${quick['monthly_savings']:,.2f}/month (${quick['monthly_savings']*12:,.2f}/year) versus {shared_ptus:g} PTUs costing ${shared_annual_cost:,.2f}/year.")
    elif quick["covers_volume"]:
        st.success(f"For this workload, use {winner.name} with PTU. The capacity covers the estimated traffic and saves ${quick['monthly_savings']*12:,.2f}/year versus PAYG.")
    else:
        st.warning("The PTU price is lower, but 50 PTUs do not cover the estimated workload. Obtain a larger capacity quote or use PAYG.")
    render_ptu_decision_summary(quick,winner,quick_cfg,workload_in,workload_out,"Show detailed quick-decision calculation")
    if explicit_tokens:
        st.caption("Explicit input/output token values from the use-case text are normalized to monthly volume and take priority. A missing output value is estimated from the selected task. Use tab 05 for manual overrides.")
    else:
        st.caption("Assumption: the stated document batch is processed once per month at approximately 850 input tokens per page. Use tab 05 to override monthly tokens, PTUs, and annual contract cost.")
    st.subheader("What-if cost for GPT-5.4 — active chat workload")
    target=next(m for m in MODELS if m.name=="GPT-5.4")
    wi_in=workload_in
    wi_out=workload_out
    a=payg_monthly_cost(target,wi_in,wi_out); b=payg_monthly_cost(winner,wi_in,wi_out)
    st.caption(f"Uses the chat-derived workload automatically: {wi_in/1_000_000:.1f}M monthly input tokens and {wi_out/1_000_000:.1f}M monthly output tokens.")
    show_metrics([("GPT-5.4 monthly PAYG",f"${a:,.2f}"),(f"{winner.name} monthly PAYG",f"${b:,.2f}"),("Difference",f"${abs(a-b):,.2f}")])

with tabs[1]:
    st.caption("02 · MODEL TABLE"); st.header("All models")
    st.markdown(f'<div class="note"><b>Active chat workload:</b> {html.escape(q)} · Recommended: {winner.name}</div>',unsafe_allow_html=True)
    st.markdown('<div class="note"><b>Benchmark:</b> “Intel” is the Artificial Analysis Intelligence Index v4.1. Scores for reasoning models depend on the stated effort configuration; open each model in “04 Explain Model” for its configuration note.</div>',unsafe_allow_html=True)
    vendors=["All"]+sorted({m.vendor for m in MODELS})
    c1,c2,c3=st.columns(3)
    vendor=c1.selectbox("Vendor",vendors,help="Filter the inventory to one model provider.")
    openness=c2.selectbox("Open weights",["All","Yes","No"],help="Open weights can support self-hosting and strict data-residency patterns.")
    vision=c3.selectbox("Vision",["All","Yes","No"],help="Vision models can accept images/scanned documents; this is distinct from image generation.")
    filtered=[m for m in MODELS if (vendor=="All" or m.vendor==vendor) and (openness=="All" or m.open_weight==(openness=="Yes")) and (vision=="All" or m.vision==(vision=="Yes"))]
    filtered_rows=model_rows(filtered)
    for row,model in zip(filtered_rows,filtered): row["Active Rank"]=active_rank.get(model.name,"—")
    render_result_table(filtered_rows,list(filtered_rows[0]) if filtered_rows else [])

with tabs[2]:
    st.caption("03 · USE CASES"); st.header("Known use cases")
    st.markdown(f'<div class="note"><b>Inferred from chat:</b> {uc.name} — {uc.category}</div>',unsafe_allow_html=True)
    needle=st.text_input("Filter",placeholder="type keyword")
    for category in sorted({u.category for u in USE_CASES}):
        group=[u for u in USE_CASES if u.category==category and needle.lower() in (u.name+" "+" ".join(u.keywords)).lower()]
        if group:
            with st.expander(category):
                for u in group: st.write(f"**{u.name}** — complexity {u.complexity}/5 · latency {u.latency}/5 · volume {u.volume}/5 · context {u.context}/5  \n{u.note}")

with tabs[3]:
    st.caption("04 · EXPLAIN MODEL"); st.header("Per-parameter justification")
    st.markdown(f'<div class="note"><b>Active chat recommendation:</b> {winner.name} for {html.escape(q)}</div>',unsafe_allow_html=True)
    m=st.selectbox("Model",MODELS,format_func=model_display,key="explain")
    st.markdown(f'<div class="note">{m.notes}</div>',unsafe_allow_html=True)
    show_metrics([("Vendor",m.vendor),("Released",m.release_date),("Knowledge cutoff",m.knowledge_cutoff),("Open weights","yes" if m.open_weight else "no")])
    params=[("intelligence",m.intelligence),("speed",f"{m.speed} tok/s"),("ttft",f"{m.ttft}s"),("input_price",f"${m.input_price}/M"),("output_price",f"${m.output_price}/M"),("context",f"{m.context:,}"),("vision",m.vision),("audio_input",m.audio_input),("video_input",m.video_input),("image_gen",m.image_gen)]
    for p,v in params: st.markdown(f"**{p.replace('_',' ').title()}: `{v}`**  \n{m.justify(p)}")

with tabs[4]:
    st.caption("05 · PTU VS PAY-AS-YOU-GO (AZURE)"); st.header("PTU vs. Pay-As-You-Go — is reserved capacity worth it?")
    use_chat_workload=st.checkbox("Use workload entered in 01 Recommend",value=True,key="ptu_use_chat")
    if use_chat_workload:
        selected_uc=uc; suggested_model=winner; suggested_in=workload_in; suggested_out=workload_out
        workload_shape=f"{docs:,} documents × {pages:g} pages" if is_document_workload else f"{requests or 1_000:,} generations/month"
        st.markdown(f'<div class="note"><b>Active chat workload:</b> {html.escape(q)}<br>{workload_shape} · recommended model {winner.name}.</div>',unsafe_allow_html=True)
    else:
        selected_uc=st.selectbox("Use case to evaluate",USE_CASES,
                                 format_func=lambda x:f"{x.name} — {x.category}",key="ptu_use_case")
        suggested_model=rank_models(selected_uc)[0][0]
        suggested_in,suggested_out=estimate_monthly_tokens(selected_uc)
    st.markdown(
        f'<div class="note"><b>Use-case planning profile:</b> {selected_uc.name} recommends '
        f'{suggested_model.name}; volume tier {selected_uc.volume}/5 estimates '
        f'{suggested_in/1_000_000:g}M input and {suggested_out/1_000_000:g}M output tokens/month.</div>',
        unsafe_allow_html=True)
    m,mi,mo,cfg=ptu_inputs("ptu_",suggested_model,suggested_in,suggested_out,
                           default_ptus=50.0,default_pricing="Annual contract total",
                           annual_contract_default=162_000.0,simple_annual=True,
                           shared_ptus=shared_ptus,shared_annual_cost=shared_annual_cost)
    r=compare_ptu_vs_payg(m,cfg,mi,mo)
    if not payg_is_verified(m):
        st.warning(f"PAYG=False for {m.name}: no comparable first-party or named managed per-token endpoint is verified. PAYG cost below is an estimate for planning only.")
    st.subheader("Calculation methodology")
    if use_chat_workload and is_document_workload:
        output_ratio=(mo/mi*100) if mi else 0
        st.markdown(f"""
**A. Workload → token volume**

`{docs:,} documents × {pages:g} pages/document × 850 input tokens/page = {workload_in:,.0f} monthly input tokens`

The selected task applies an estimated output ratio of **{output_ratio:.1f}%**, producing **{workload_out:,.0f} monthly output tokens**. Both values can be overridden under **Monthly token volume and capacity overrides**.
""")
    elif use_chat_workload:
        st.markdown(f"""
**A. Workload → token volume**

`{users or 'unspecified'} users × {per_user or 'unspecified'} generations/user = {requests or 1_000:,} monthly generations`

Planning estimate: **{mi:,.0f} monthly input tokens** and **{mo:,.0f} monthly output tokens**. Explicit chat token values take priority. Image-generation charges are separate from text-token PAYG pricing.
""")
    st.markdown(f"""
**B. PAYG cost**

`PAYG monthly cost = (monthly input tokens ÷ 1,000,000 × input $/M) + (monthly output tokens ÷ 1,000,000 × output $/M)`

**C. PTU contract cost**

`PTU monthly cost = total annual PTU contract cost ÷ 12`

`Effective $/PTU/hour = annual contract cost ÷ (number of PTUs × 730 hours/month × 12 months)`

**D. Capacity demand**

`Output capacity weight = model output price ÷ model input price` unless manually overridden. For **{m.name}**, the current weight is **{r['output_weight_used']:.2f}×**.

`Weighted monthly tokens = input tokens + (output tokens × output capacity weight)`

`Required TPM = weighted monthly tokens ÷ (730 × 60 monthly minutes)`

**E. PTU capacity and utilization**

`Available TPM = number of PTUs × model-specific TPM per PTU`

`PTUs required = required TPM ÷ TPM per PTU`

`Utilization % = required TPM ÷ available TPM × 100`

**F. Break-even and recommendation**

`Cost break-even multiplier = PTU monthly cost ÷ PAYG monthly cost`

PTU is recommended only if **available TPM ≥ required TPM** and **PTU monthly cost < PAYG monthly cost**. Otherwise, PAYG is recommended. A nominally cheaper PTU contract is rejected when it cannot serve the workload.
""")
    st.subheader("Throughput and utilization")
    show_metrics([("Required TPM",f"{r['required_tpm']:,.0f}"),("Available TPM",f"{r['available_tpm']:,.0f}"),("PTUs needed",f"{r['ptus_needed']:.1f}"),("Utilization",f"{r['utilization_pct']:.1f}%" if r['utilization_pct'] is not None else "—")])
    st.subheader("Cost comparison")
    show_metrics([("PTU monthly cost",f"${r['ptu_monthly_cost']:,.2f}"),("PAYG monthly cost",f"${r['payg_monthly_cost']:,.2f}"),("Cheaper option",r['cheaper_option'])])
    annual_savings=r['monthly_savings']*12
    if r['cheaper_option']=="PTU" and r["covers_volume"]:
        st.success(f"Recommendation for {selected_uc.name}: choose PTU. It covers the workload and saves ${r['monthly_savings']:,.2f}/month (${annual_savings:,.2f}/year) versus PAYG.")
    elif r['cheaper_option']=="PTU":
        st.error(f"PTU appears cheaper but the quoted capacity does not cover {selected_uc.name}; use PAYG or obtain a larger PTU quote.")
    else:
        st.info(f"Recommendation for {selected_uc.name}: choose PAYG. At this volume it saves ${r['monthly_savings']:,.2f}/month (${annual_savings:,.2f}/year) versus the PTU contract.")
    if not r["covers_volume"]: st.error("The selected PTU capacity does not cover this monthly volume.")
    render_ptu_decision_summary(r,m,cfg,mi,mo)
    st.caption("PTU defaults are planning estimates. Verify rate, capacity and regional availability with Azure before committing budget.")

with tabs[5]:
    st.caption("06 · DECISION COCKPIT (BUSINESS)"); st.header("Side-by-side model comparison for a business decision")
    st.markdown(f'<div class="note"><b>Active chat workload:</b> {html.escape(q)} · {workload_in/1_000_000:.1f}M input / {workload_out/1_000_000:.1f}M output tokens per month.</div>',unsafe_allow_html=True)
    st.caption(f"Synchronized with Recommendation Top N: comparing the same top {top_n} ranked models. Change Top N in tab 01 to update this set.")
    default_compare=active_top_models
    dcmodel_kwargs={} if "dcmodels" in st.session_state else {"default":default_compare}
    selected=st.multiselect("Models to compare",MODELS,format_func=model_display,key="dcmodels",**dcmodel_kwargs)
    c1,c2,c3=st.columns(3)
    dcin_kwargs={} if "dcin" in st.session_state else {"value":float(workload_in)}
    dcout_kwargs={} if "dcout" in st.session_state else {"value":float(workload_out)}
    mi=c1.number_input("Monthly input tokens",0.0,key="dcin",**dcin_kwargs)
    mo=c2.number_input("Monthly output tokens",0.0,key="dcout",**dcout_kwargs)
    c3.metric("PTUs available",f"{shared_ptus:g}",help="Shared PTU quantity from the sidebar.")
    ptus=shared_ptus
    st.subheader("Score weighting — adjust to match your organisation's priorities")
    c1,c2,c3,c4=st.columns(4)
    qw=c1.slider("Quality %",0,100,50,help="Weight assigned to normalized Intelligence Index quality within the selected comparison set.")
    ew=c2.slider("Economics %",0,100,30,help="Weight assigned to the inverse effective monthly cost after choosing viable PTU or PAYG.")
    lw=c3.slider("Latency %",0,100,10,help="Weight assigned to lower time-to-first-token within the selected comparison set.")
    rw=c4.slider("Risk/Compliance %",0,100,10,help="Planning score based on reasoning support, vision capability and open-weight availability; replace with organizational controls for production governance.")
    rows=[]
    if selected:
        maxintel=max((m.intelligence or 0) for m in selected) or 1; maxcost=max(payg_monthly_cost(m,mi,mo) for m in selected) or 1; maxttft=max(m.ttft for m in selected) or 1
        for m in selected:
            cockpit_hourly=shared_annual_cost/(max(ptus,1)*730*12)
            cfg=PTUConfig(ptus,cockpit_hourly); p=compare_ptu_vs_payg(m,cfg,mi,mo); effective=min(p["payg_monthly_cost"],p["ptu_monthly_cost"]) if p["covers_volume"] else p["payg_monthly_cost"]
            quality=(m.intelligence or 0)/maxintel*100; economics=(1-effective/maxcost)*100; latency=(1-m.ttft/maxttft)*100; risk=(20 if m.open_weight else 0)+(30 if m.reasoning else 0)+(20 if m.vision else 0)
            total=(quality*qw+economics*ew+latency*lw+risk*rw)/max(qw+ew+lw+rw,1)
            billing=p['cheaper_option'] if payg_is_verified(m) or p['cheaper_option']!='PAYG' else "PAYG estimate (unverified)"
            rows.append({"Model":model_display(m),"Vendor":m.vendor,"PAYG Verified":payg_is_verified(m),"PAYG $/mo":round(p['payg_monthly_cost'],2),"PTU $/mo":round(p['ptu_monthly_cost'],2),"PTU Covers":p['covers_volume'],"Required TPM":round(p['required_tpm']),"Available TPM":round(p['available_tpm']),"Utilization %":round(p['utilization_pct'] or 0,1),"Cheaper Billing":billing,"Effective $/mo":round(effective,2),"Quality":round(quality,1),"Economics":round(economics,1),"Latency":round(latency,1),"Risk/Compliance":round(risk,1),"Weighted Score":round(total,1)})
        rows.sort(key=lambda x:x["Weighted Score"],reverse=True); winner=rows[0]
        st.subheader("Live weighted score by model")
        st.caption(f"Score = Quality × {qw}% + Economics × {ew}% + Latency × {lw}% + Risk/Compliance × {rw}%, divided by the total active weight. Change any slider to recalculate every model immediately.")
        render_weighted_scores(rows)
        show_metrics([("Recommended for rollout",winner["Model"]),("Best billing path",winner["Cheaper Billing"]),("Weighted score",winner["Weighted Score"])])
        st.subheader("Executive Summary (1-minute read)"); show_metrics([("Recommended model",winner["Model"]),("Estimated annual run cost",f"${winner['Effective $/mo']*12:,.2f}"),("Annual savings vs #2",f"${(rows[1]['Effective $/mo']-winner['Effective $/mo'])*12:,.2f}" if len(rows)>1 else "$0")])
        render_result_table(rows,list(rows[0]))
        buf=io.StringIO(); writer=csv.DictWriter(buf,fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
        st.download_button("Download comparison CSV",buf.getvalue(),"model_comparison.csv","text/csv")
