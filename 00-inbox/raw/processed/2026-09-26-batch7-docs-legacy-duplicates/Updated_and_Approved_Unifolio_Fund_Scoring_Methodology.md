# Unifolio 

UNIFOLIO — PROPRIETARY FUND SCORING METHODOLOGY 

## **1. Overview** 

The Unifolio Fund Score answers one question as precisely as the available data allows: how good is this fund, really — compared to its true category peers? Every fund is scored only against other funds in its own SEBI scheme category, so a Large Cap fund is never compared to a Mid Cap, Small Cap, or Flexi Cap fund. 

The score is built from ten weighted components across six buckets — Return, Consistency, Downside Risk, Risk-Adjusted Efficiency, Upside Participation, Valuation, and Cost Efficiency — combined into a single 0–100 score. Every published score is shown together with its full component breakdown; the methodology is designed to be fully explainable, never a black-box number. 

## **2. Scoring Attributes and Weights** 

Each component below is first converted into the fund’s percentile rank within its own category (0–100, higher is always better), and the weights below are then applied to those percentiles — not to the raw metric values directly. 

|**Bucket**|**Component**|**Weight**|
|---|---|---|
|Return|Rolling return, blended 1–5Y, recency-weighted|25%|
|**Cit**|Beats category average (% of 1–5Y rolling windows)|12%|
|**onssency**|Top-quartile frequency (% of 1–5Y rolling windows)|8%|
||Max drawdown percentile|7.5%|
|**Did Rik**|||
|**ownse s**|Down Capture Ratio|7.5%|
|**Risk-Adjusted Efficiency**|Sortino|10%|
||Information Ratio|10%|
|Upside Participation|Up Capture|5%|
|Valuation Overlay|PE/PB vs category average (relative, not absolute)|5%|
|**Cost Efficienc**|Expense ratio level vs category average|6%|
|**y**|Expense ratio trend (pattern over last 2–3 years)|4%|
|**Total**||**100%**|



Proprietary & Confidential — Page 2 of 4 

UNIFOLIO — PROPRIETARY FUND SCORING METHODOLOGY 

## **3. The Scoring Formula** 

For fund f, in category C, as of date t: 

```
  Score(f,t) = 0.25·Return + 0.12·BeatsAvg + 0.08·TopQuartileFreq
```

```
               + 0.075·Drawdown + 0.075·DownCapture
               + 0.10·Sortino + 0.10·InfoRatio
               + 0.05·UpCapture + 0.05·ValuationOverlay
```

```
               + 0.06·CostLevel + 0.04·CostTrend
```

|**Term**|**Definition**|
|---|---|
|**f**|The fund being scored|
|**C**|The fund’s SEBI scheme category (its true peer set)|
|**t**|The date as of which the score is calculated|
|**Score(f,t)**|Final Unifolio Score for fund f as of date t, on a 0–100 scale|
|**Percentile(x)**|The fund’s rank-percentile on metric x among all funds in category C as of date t.<br>0–100, higher is always better — metrics where a lower raw value is better<br>(drawdown, expense level, PE/PB deviation) are inverted before ranking.|



## **4. Methodology Notes** 

### **4.1 Recency Weighting** 

Within the Return and Consistency components, rolling windows are weighted so that more recent periods (e.g. 2023–2025) carry more influence than distant ones (e.g. 2018–2020). This ensures the score reflects the fund as it is managed today, rather than a track record inherited from a manager or process no longer in place. 

### **4.2 The Expense Ratio Pattern** 

Cost is scored on two independent signals rather than a single snapshot: 

- Level (6%): the fund’s current expense ratio relative to its category average. The adjustment only activates once the gap is meaningful — small differences are treated as noise. 

- Trend (4%): the direction of the expense ratio over the last 2–3 years, assessed independently of the current level. A ratio falling as AUM grows signals scale benefits being passed to investors. A ratio rising without AUM growth — or rising while AUM is flat or shrinking — signals margin protection at the investor’s expense. A flat ratio is treated as neutral. 

Proprietary & Confidential — Page 3 of 4 

UNIFOLIO — PROPRIETARY FUND SCORING METHODOLOGY 

This distinguishes a fund that is cheap today and has been getting cheaper from a fund that is cheap today but has been quietly raising fees — a pattern a single-point snapshot would miss entirely. 

### **4.3 Valuation Overlay** 

PE and PB are scored relative to the fund’s own category average, not on an absolute “lower is better” scale. Valuation reflects investment style (value vs. growth orientation) rather than fund quality, and is deliberately weighted small (5%) so it nudges, rather than dominates, the final score. 

### **4.4 Risk-Adjusted Efficiency** 

Sortino Ratio and Information Ratio were selected as the two representative risk-adjusted metrics because they capture the two risk concepts most relevant to comparing actively managed equity funds within the same category: downside deviation (how much is lost in bad months) and tracking error (how much the fund deviates from its benchmark). Both are reported as category percentiles. 

## **5. Data Requirements and Gating Rules** 

A score is only shown to users once the underlying data meets the following minimum standards: 

- Minimum track record: a full score requires at least 3 years of NAV history. Funds with 1–3 years of history receive a provisional score with a visible flag. Funds with under 1 year of history are not scored. 

- Minimum peer set: percentile ranking requires a minimum category size (e.g. 15 funds) to be considered statistically reliable. Categories below this threshold are either widened or the resulting score is flagged as low-confidence. 

- No silent data substitution: where an input metric cannot be calculated for a fund (insufficient history, missing holdings, or data-provider gaps), that component is excluded from both the score and its weighting denominator. A fund is never scored, rewarded, or penalised on data that is not actually available. 

## **6. What This Score Is — and Is Not** 

The Unifolio Score is a modelling opinion built on historical, point-in-time data. It is not a guarantee of future performance, and it is not a neutral, universally agreed-upon fact about a fund. Reasonable methodologies can and do disagree on how to weigh return, risk, and consistency; this is one considered, transparently documented point of view — not the only possible answer — and it is never presented to users as anything more than that. 

Proprietary & Confidential — Page 4 of 4 

