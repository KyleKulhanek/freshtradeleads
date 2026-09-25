# FreshTradeLeads inventory analysis

Source anchor: **2026-09-02**. Windows contain exactly N calendar dates ending on the anchor.

Southern California is defined only as: Los Angeles, Orange, Riverside, San Bernardino, San Diego, Ventura.

## Candidate score

Score = 30% lead-count fit (favoring 20–75) + 20% phone completeness + 20% CLEAR status + 15% trade relevance to insurance/surety + 10% geography clarity + 5% recency. It is a transparent ranking heuristic, not an ML model.

## Highest-volume statewide classifications, 30 days

| Code | Description | Leads | CLEAR | Phone |
|---|---|---:|---:|---:|
| B | General Building Contractor | 514 | 99.8% | 99.8% |
| C10 | Electrical Contractor | 147 | 100.0% | 99.3% |
| C36 | Plumbing Contractor | 111 | 100.0% | 99.1% |
| C27 | Landscaping Contractor | 71 | 98.6% | 100.0% |
| C33 | Painting and Decorating Contractor | 69 | 100.0% | 100.0% |
| C20 | Warm-Air Heating, Ventilating and Air-Conditioning Contractor | 65 | 100.0% | 100.0% |
| A | General Engineering Contractor | 57 | 100.0% | 100.0% |
| C39 | Roofing Contractor | 49 | 100.0% | 100.0% |
| C-8 | Concrete Contractor | 31 | 100.0% | 100.0% |
| C49 | Tree and Palm Contractor | 26 | 100.0% | 100.0% |
| C-7 | Low Voltage Systems Contractor | 24 | 100.0% | 100.0% |
| D28 | Doors, Gates and Activating Devices Contractor | 23 | 100.0% | 100.0% |
| C54 | Ceramic and Mosaic Tile Contractor | 22 | 100.0% | 100.0% |
| B-2 | Residential Remodeling Contractor | 21 | 100.0% | 100.0% |
| C15 | Flooring and Floor Covering Contractor | 21 | 100.0% | 100.0% |

## Highest-volume counties, all trades, 30 days

| County | Newly issued licenses |
|---|---:|
| Los Angeles | 324 |
| Orange | 129 |
| San Diego | 119 |
| Riverside | 109 |
| Sacramento | 65 |
| Santa Clara | 64 |
| San Bernardino | 63 |
| (missing) | 57 |
| Contra Costa | 38 |
| Alameda | 37 |
| Ventura | 36 |
| San Joaquin | 28 |
| Fresno | 23 |
| Stanislaus | 22 |
| Sonoma | 19 |

## Recommended initial products

### 1. New Electrical Contractors — Southern California, Last 14 Days

- Leads: 47; score: 98.78; suggested price: $29
- Audience: Commercial insurance and surety professionals serving contractors
- Ad hook: Reach 47 newly licensed electrical contractor businesses in Southern California before established lead lists catch up.
- Sample: `/opt/freshtradeleads/data/exports/candidate_1_c10_southern_california_14d.xlsx`

### 2. New General Building Contractors — San Diego, Last 30 Days

- Leads: 49; score: 98.35; suggested price: $29
- Audience: Commercial insurance and surety professionals serving contractors
- Ad hook: Reach 49 newly licensed general building contractor businesses in San Diego before established lead lists catch up.
- Sample: `/opt/freshtradeleads/data/exports/candidate_2_b_san_diego_30d.xlsx`

### 3. New Roofing Contractors — California, Last 30 Days

- Leads: 49; score: 95.85; suggested price: $29
- Audience: Commercial insurance and surety professionals serving contractors
- Ad hook: Reach 49 newly licensed roofing contractor businesses in California before established lead lists catch up.
- Sample: `/opt/freshtradeleads/data/exports/candidate_3_c39_california_30d.xlsx`

### 4. New Electrical Contractors — Los Angeles, Last 30 Days

- Leads: 38; score: 94.87; suggested price: $15
- Audience: Commercial insurance and surety professionals serving contractors
- Ad hook: Reach 38 newly licensed electrical contractor businesses in Los Angeles before established lead lists catch up.
- Sample: `/opt/freshtradeleads/data/exports/candidate_4_c10_los_angeles_30d.xlsx`

### 5. New Warm-Air Heating, Ventilating and Air-Conditioning Contractors — Southern California, Last 30 Days

- Leads: 39; score: 94.8; suggested price: $15
- Audience: Commercial insurance and surety professionals serving contractors
- Ad hook: Reach 39 newly licensed warm-air heating, ventilating and air-conditioning contractor businesses in Southern California before established lead lists catch up.
- Sample: `/opt/freshtradeleads/data/exports/candidate_5_c20_southern_california_30d.xlsx`

## Data fitness

Recent 30-day records are classified as clean (1224), usable with caveat (128), or questionable (0).

| Field | Complete | Percent |
|---|---:|---:|
| Business Name | 1352 | 100.0% |
| Phone | 1349 | 99.8% |
| Address | 1352 | 100.0% |
| City | 1352 | 100.0% |
| County | 1295 | 95.8% |
| Zip | 1352 | 100.0% |
| Classification | 1352 | 100.0% |
| Issue Date | 1352 | 100.0% |
| Status | 1352 | 100.0% |
| Workers Comp Type | 1352 | 100.0% |
| Workers Comp Carrier | 407 | 30.1% |
| Bond Surety | 1352 | 100.0% |
| Bond Amount | 1352 | 100.0% |

Structural anomaly counts are retained in `data/processed/commercial_quality_audit.json`; questionable source values are not guessed or rewritten.

Policy numbers, disciplinary case identifiers/reasons, and person-level names should not be sold in the MVP. Workers-comp carrier should be displayed only when the coverage type is actual insurance; its overall missing rate mostly reflects exempt or no-current-coverage records rather than corruption.
