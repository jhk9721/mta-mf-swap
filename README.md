# mta-mf-swap
Comparing Roosevelt Island headways before and after F/M swap

# What we did, start to finish
Last December, the MTA swapped which train serves Roosevelt Island on weekdays. The F train, which had been running there since the 80s, was replaced by the M train during the day. The MTA claimed this would improve reliability for the broader system and promised that Roosevelt Island riders would only wait about one extra minute.

A group of Roosevelt Island residents felt their lived experience did not match this claim, so they decided to check.

The MTA publishes real-time train location data — essentially a live feed of where every train in the system is at any given moment. A website called subwaydata.nyc archives that feed every single day. We downloaded nearly 40,000 individual train arrival records for Roosevelt Island, covering about five months, including before the swap and after it.

We then measured something called a "headway" (how many minutes passed between one train arriving and the next one arriving). We did this for every train, every day, to answer the question: Are trains coming more or less frequently than before?

The answer was stark. During the evening commute home, the gap between trains more than doubled, from about 4 minutes to about 8 minutes. During the morning commute to Manhattan, it went up 71%. Every single time period got worse. The MTA's promised "about 1 extra minute" turned out to be an extra 3 to 4 minutes in practice.

We then found the MTA's own internal planning document from before the swap was implemented. It was signed by their Chief of Operations Planning and approved all the way up to the MTA President. That document explicitly admitted Roosevelt Island would face longer waits — and made a specific written promise to add extra M train service to mitigate the impact to roughly one extra minute of wait time. We can now show, with their own data, that the promise was not kept.
We also built a public interactive website where anyone can explore the data themselves. And we put everything, including the raw data, the code, and the methodology, on GitHub so that anyone, including the MTA, can check our work.

Roosevelt Island has one subway station and no alternative line. When service gets worse there, residents have nowhere else to go. That's why this matters, and why having documentation that holds the MTA to its own written commitments is worth the effort.

# Methodology

This section explains, in plain language, every decision we made in this analysis — what we did, why we did it that way, and where reasonable people might disagree. We've tried to be honest about the limitations of our approach, not just the strengths.

---

## The core question

On December 8, 2025, the MTA replaced the F train with the M train at Roosevelt Island Station on weekdays, between 6:00 AM and 9:30 PM. The MTA claimed this would improve reliability for the broader system. We wanted to know what actually happened to wait times at Roosevelt Island.

We measured this using **headways** — the gap in minutes between one train arriving and the next. A headway of 5 minutes means trains are running every 5 minutes. If headways get longer after the swap, riders are waiting longer.

---

## Why we built this ourselves

The MTA publishes scheduled headways and departure times — how often trains are *supposed* to run. However, scheduled and actual times tend to be dramatically different, given the size and complexity of the NYC transit system. A train that's supposed to come every 6 minutes might run every 10 in practice. We wanted to measure what riders actually experienced on the platform, not what the MTA planned on paper.

The only way to do that is to use the MTA's own real-time location data, archived over time.

---

## Data source

We used **[subwaydata.nyc](https://subwaydata.nyc)**, a website that archives the MTA's GTFS real-time feed every day. The GTFS (General Transit Feed Specification) real-time feed is the same data that powers apps like Google Maps and Citymapper — it's a continuous stream of train positions broadcast by the MTA itself.

The critical difference between subwaydata.nyc and most transit apps is **completeness**. Most apps poll the feed periodically — they check in every few minutes and record what they see. subwaydata.nyc captures the full feed continuously. That means if a train comes and goes between two polling checks, subwaydata.nyc captures it; a polling-based system misses it entirely.

---

## `1_download.py` — Pulling the raw data

**What it does:** Downloads compressed archives of MTA real-time data for five months: October and November 2025 (before the swap), December 2025 (the swap happened on December 8), and January and February 2026 (after the swap). Each day is a separate compressed file containing the train location records for that day. The total download is roughly 300–600 MB.

**Why these months:** We needed enough data before and after the swap to distinguish a real change from natural day-to-day variation. Ten weeks on each side gives us that statistical confidence. We started on October 1 rather than September 1 deliberately — September includes Labor Day and the tail end of summer schedules, which would add noise to the baseline. Starting in October gives us clean, settled weekday service.

**Why not go back further:** More history isn't always better. Going back a year would introduce seasonal variation (summer ridership, holiday schedules) that would confound the comparison. Our goal was a clean like-for-like: the same station, the same season, before and after one specific change.

---

## `1b_download_extended.py` — Extended download for seasonality testing

**What it does:** Downloads additional months of data not covered by `1_download.py`, serving two purposes: (1) provides a year-ago F train baseline (January–February 2025) to directly test whether winter seasonality — rather than the swap — explains the headway increase; and (2) fills any gaps left by `1_download.py` and extends the post-swap trend through the current date. Files already on disk are skipped automatically, so re-runs are safe.

**Why this matters:** A legitimate question raised after the initial analysis was whether January and February are simply worse months for subway service regardless of who's running the train. By downloading January–February 2025 data (F train, same season as the post-swap period), we can run a direct year-over-year comparison. If winter conditions were the main driver, the pre-swap winter (2025) and post-swap winter (2026) should look similar. They don't — which isolates the swap as the cause.

**Run order:** Run `1_download.py` first, then this script. All files land in the same `raw_data/` folder and are picked up automatically by the analysis scripts.

**Estimated download:** ~130 additional days of data, roughly 260–520 MB. Allow 15–30 minutes depending on your connection.

---

## `2_inspect.py` — Verifying we have the right data

**What it does:** Opens one of the downloaded files and prints its contents — column names, sample rows, and a search for Roosevelt Island records. It also specifically looks for what stop IDs appear in the data.

**Why this step matters:** This was where we discovered a critical issue. Our initial assumption was that Roosevelt Island's GTFS stop ID was **F09**. The inspect script showed that it was the wrong stop ID; the data uses **B06**. B06N for the northbound platform, B06S for the southbound platform.

We verified this against the official MTA Station & Complexes glossary published on data.ny.gov (February 2026 edition). This step saved the entire analysis from being based on the wrong station. If we had filtered on F09, we would have had zero records and concluded there was no data — or worse, accidentally analyzed a different station.

**The lesson:** Never assume stop IDs. Always verify against the official source before doing any analysis.

---

## `3_analyze.py` — Computing the headways

This is the core of the analysis. It does several things in sequence.

### Loading and filtering to Roosevelt Island

The raw data contains every train at every station in the MTA system — hundreds of thousands of records per day. We filter to records where the stop ID is B06N or B06S (Roosevelt Island only) and where the route is F or M (the lines that serve the station).

### Deriving direction from stop ID

The raw data gives us a stop ID (B06N or B06S) and a direction_id (0 or 1). Rather than relying on the direction_id field — which has an arbitrary encoding — we derive direction from the last character of the stop ID: N means northbound, S means southbound.

We then verified which physical direction each letter corresponds to. The 63rd Street line runs roughly northeast-southwest. During morning rush, we'd expect more trains heading toward Manhattan (southbound). Checking the data confirmed: the S direction has higher train frequency and shorter headways during the 6–9 AM rush. So:

- **N = Northbound = toward Queens** — the evening commute home
- **S = Southbound = toward Manhattan** — the morning commute to work

This is counterintuitive to anyone who thinks of Manhattan as "uptown" or "north." It isn't on this line. We flag this prominently because it's a common source of confusion when people review the analysis.

### Computing headways

For each day, for each direction, for each time period, we sort the train arrivals in chronological order and calculate the gap between consecutive arrivals. That gap is the headway.

**Why within-group calculation matters:** We compute headways separately for each direction and each time bucket within each day. We don't compute headways across midnight, across direction changes, or across time period boundaries. This prevents artifacts like a "headway" that spans overnight or crosses from one time period into another.

### Outlier handling

Two types of outliers appear in the data:

**Short headways (< 1 minute):** We assume these represent duplicate records — the same train appearing twice in the feed with slightly different timestamps. It is unlikely that a train arrives less than a minute after the previous one on this line. Furthermore, two trains arriving within less than a minute of one another, followed by a long wait time, still results in residents waiting on the platform for long periods of time. Therefore, we drop all values below 1 minute.

**Long headways (> 60 minutes):** These represent genuine service gaps — a train that simply didn't come for an extended period. They do happen, but they're rare enough that including them would distort the median. We cap at 60 minutes for most time periods. For the overnight bucket (midnight to 6 AM), we raise the cap to 90 minutes, because overnight service genuinely runs much less frequently and a 70-minute gap is plausible.

We use the **median** throughout, not the mean. The median is the middle value — half of the waits were shorter, half were longer. The mean would be dragged upward by occasional very long gaps (a signal failure, say) and would overstate the typical rider experience. The median tells you what a typical ride was actually like.

### Time buckets

We divide the day into five periods based on clock time:

| Bucket | Hours | Notes |
|---|---|---|
| Early AM | Midnight – 6 AM | F train throughout (swap inactive) |
| Morning Rush | 6 AM – 9 AM | Swap active on weekdays |
| Midday | 9 AM – 4 PM | Swap active on weekdays |
| Evening Rush | 4 PM – 7 PM | Swap active on weekdays |
| Night | 7 PM – midnight | Partially active (swap ends 9:30 PM) |

The same clock-based buckets apply to every day of the week. Weekdays and weekends get different labels in the charts (because the swap is weekday-only), but the underlying time boundaries are identical. This ensures consistency and avoids any appearance of cherry-picking time windows.

**Why 4–7 PM for evening rush, not 4–8 PM:** The swap ends at 9:30 PM, and the genuine rush is concentrated in 4–7 PM. Extending the bucket would dilute the peak-hour finding with lower-ridership hours. The 4–7 PM window captures when the impact is most acute and when the most people are affected.

### Holiday weeks

The analysis includes the holiday period (December 22 – January 5). We considered excluding it because lower ridership during the holidays might affect headways. When we checked, excluding the holiday weeks made the post-swap numbers slightly *worse*, not better — service frequency was actually somewhat lower during that period, possibly reflecting reduced service for lower-ridership expectations. We include holidays in our published numbers because excluding them would make our findings appear weaker than they actually are. We flag this transparently.

### The January 25 storm

A significant winter storm hit New York on January 25, 2026. We ran the analysis three ways: including all post-swap data, excluding the storm period (January 25 onward), and comparing just December 8 – January 24. The results:

| Period | Median headway | vs. Pre-swap |
|---|---|---|
| Pre-swap (Oct 1–Dec 7) | 5.25 min | — |
| Post-swap, pre-storm (Dec 8–Jan 24) | 8.08 min | **+54%** |
| Post-storm (Jan 25–Feb 15) | 8.38 min | **+60%** |

The storm accounts for approximately 6 percentage points of the total increase in wait times. The swap accounts for the other 54. We report the conservative (pre-storm) figure of +54% as our headline, where precision matters, and note that the full period figure is +60%.

---

## `4_community_output.py` — Generating the charts

**What it does:** Takes `results/roosevelt_island_headways.csv` — the processed headway data produced by `3_analyze.py` — and produces eight charts and a set of talking points designed for community use. The headways CSV has been updated to incorporate the extended date range from `1b_download_extended.py`, covering January–April 2025 (year-ago baseline) and the full post-swap period through March 2026.

**Chart design decisions:**

We show the **median** as the primary bar, with a **90th percentile triangle** above it. The 90th percentile is the "worst 1-in-10" wait — the kind of delay that, while not typical, happens regularly enough that regular commuters will encounter it several times a month. Both statistics matter: the median tells you the typical experience, the 90th percentile tells you the risk exposure.

The **long-wait frequency charts** show the percentage of train intervals exceeding specific thresholds (5, 8, 10, 12, and 15 minutes). These translate the abstract headway numbers into something more concrete: "1 in 3 times you wait for a northbound train during the evening, you'll wait more than 10 minutes." That's a different kind of comprehensible than "+111%."

The **weekend charts** serve a specific analytical purpose. Since the swap is weekday-only, the F train serves Roosevelt Island on weekends in both periods. Any changes in weekend headways cannot be attributed to the swap — they reflect broader changes to F train service system-wide. We include this chart both for completeness and as a methodological check: if weekends were also dramatically worse, a skeptic might argue the whole F line degraded and our weekday numbers aren't specifically about the swap. The weekend data lets us isolate the swap's contribution.

---

## `6_analyze_63rd_st_line.py` — Confirming the degradation at all three stations

**What it does:** Extends the Roosevelt Island analysis to all three stations on the 63rd Street line — 21 St-Queensbridge (B04), Roosevelt Island (B06), and Lexington Av/63 St (B08) — and confirms that headway degradation is identical at all three. A route filter (F/FX pre-swap, M post-swap) is applied at every station to isolate the 63rd Street line service. This is especially important at B08, which is also served by the Q train; without the filter, Q arrivals would artificially compress measured headways there.

**Why this matters:** After applying the route filter, arrival counts at all three stations are within 1% of each other in every time bucket and direction. Median headways vary by at most 0.1–0.2 minutes across stations — which is expected, since the same physical trains stop at B04, B06, and B08 sequentially with no branching. The three-station agreement is independent methodological validation: it rules out the possibility that Roosevelt Island's numbers are a station-specific data artifact. The degradation is a line-level service change.

**Run order:** Run `1_download.py` and `1b_download_extended.py` first. This script is otherwise standalone — it does not depend on `3_analyze.py`.

**Outputs** (saved to `results/63rd_st_line/`):
- `63rd_st_headways.csv` — headway records for all three stations
- `63rd_st_summary.csv` — median/p90 before vs. after by station
- `63rd_st_comparison_southbound.png`, `63rd_st_comparison_northbound.png` — side-by-side bar charts for each direction
- `63rd_st_daily_trend.png` — daily rolling median over time, all three stations overlaid
- `63rd_st_report.txt` — plain-English findings

---

## `7_analyze_m_train_frequency.py` — Measuring the MTA's promised 6-minute headway

**What it does:** Directly tests whether the MTA delivered the enhanced M train service it committed to in its September 2025 Staff Summary. That document promised that adding extra peak M trains would bring headways to 6.0 minutes, limiting the wait time increase to approximately one minute over the F train's 4.0-minute headways. This script compares actual post-swap M train headways at Roosevelt Island against that 6.0-minute benchmark, and tracks whether service has improved month by month since the swap.

**Why this matters:** The MTA made two distinct commitments: (1) the overall wait time increase would be about one minute, and (2) it would add M trains to achieve 6-minute headways. Script 7 tests the second commitment. Actual post-swap headways at Roosevelt Island have run approximately 8–9 minutes — roughly 30–50% above the promised level. The monthly trend data shows no meaningful improvement, suggesting the MTA has not taken corrective action.

**Data source:** Uses `results/roosevelt_island_headways.csv` from `3_analyze.py` if available (faster). Falls back to rebuilding from raw archives if the CSV is not present.

**Run order:** Run `1_download.py`, `1b_download_extended.py`, and `3_analyze.py` first (or just the download scripts if the fallback path is acceptable).

**Outputs** (saved to `results/m_train_frequency/`):
- `m_train_trains_per_day.csv` — average daily train counts before/after, by direction and rush window
- `m_train_headway_stats.csv` — median/p90 headways with gap vs. MTA promise
- `m_train_monthly_trend.csv` — monthly breakdown of M headways since the swap
- `m_train_vs_promise.png` — bar chart: actual F (before), actual M (after), and MTA's promised 6-minute level
- `m_train_trend_over_time.png` — monthly median headway trend with promise and pre-swap F baseline marked
- `m_train_frequency_report.txt` — plain-English findings

---

## `8_analyze_queensboro_plaza.py` — Did the MTA's stated rationale hold up?

**What it does:** Analyzes whether the MTA's stated reason for the swap — improving reliability at Queens Plaza by eliminating the local-to-express merge — produced measurable results. The script examines two separately named stations that are frequently confused in press coverage:

1. **Queens Plaza (G21)** — the E/F/R station on the Queens Blvd express tracks, directly downstream of the merge point. Pre-swap service was E, M, and R; post-swap it became E, F, and R. Headways are computed per route, so each line's arrivals are measured independently.
2. **Queensboro Plaza (718/R09)** — a completely separate station served by the 7, N, and W trains, included because it is routinely confused with Queens Plaza in official and press discussions. Its service was unaffected by the swap, so flat headways there serve as a negative control.

**Important data quality note:** The GTFS-RT feed records M train arrivals at G21 (the Queens Plaza complex ID) pre-swap, even though the M ran on the local tracks and stopped at stations like 36 St and Steinway St before the merge point. G21 appears to function as a complex-level ID that captures arrivals from both express and local platforms. The apparent post-swap improvement in E/F combined headways at G21 is largely an artifact of the M disappearing from the feed there — not a genuine reliability gain. The R train, whose route did not change, serves as the cleanest control for actual E/F/R corridor reliability.

**Run order:** Run `1_download.py` and `1b_download_extended.py` first. Standalone — no dependency on `3_analyze.py`.

**Outputs** (saved to `results/queensboro/`):
- `queensboro_headways.csv` — headway records for both stations
- `queensboro_summary.csv` — median/p90 before vs. after by station and route
- `queens_plaza_by_route_southbound.png`, `queens_plaza_by_route_northbound.png` — per-route headway charts at Queens Plaza
- `queensboro_plaza_7nw.png` — 7/N/W headways at Queensboro Plaza (expected: no change)
- `queens_plaza_long_gaps.png` — share of intervals exceeding 10 minutes per route, before/after
- `queensboro_report.txt` — plain-English findings, including advocacy framing

---

## `9_analyze_systemwide_trips.py` — Did the MTA actually run more M trains?

**What it does:** Tests a specific claim: that the MTA added extra M trains to compensate Roosevelt Island riders, as promised in its September 2025 Staff Summary. The naive approach — counting total M trip runs systemwide — is invalid because the swap changed the M's route entirely (from Middle Village–Essex St via Queens Blvd/6th Ave to Middle Village–57 St via the 63rd Street line). The same number of trip runs now covers a different route; systemwide counts say nothing about frequency at any particular station.

The correct approach is to measure M arrivals at stations that were on the M route in **both** pre-swap and post-swap periods: Queens Blvd local stations Elmhurst Av (G13), Northern Blvd (G16), and 46 St (G18). These stations see the M in both periods, so an increase in arrivals there would indicate new trains were actually added. The R train, which shares these stations and whose route did not change, serves as an internal control: flat R arrivals confirm the corridor schedule itself is stable.

**Analysis scope:** Peak hours only (6–9 AM and 4–7 PM), consistent with the MTA's own framing of its peak-hour commitment. December 2025 is excluded from all period comparisons because the swap took effect December 8, making December a split month with an uninterpretable average.

**Run order:** Run `1_download.py` and `1b_download_extended.py` first. Standalone — no dependency on `3_analyze.py`.

**Outputs** (saved to `results/m_train_frequency_control/`):
- `control_station_arrivals.csv` — daily M and R peak arrivals per control station
- `control_station_summary.csv` — before/after averages with % change
- `control_monthly.csv` — monthly average arrivals, M and R
- `control_arrivals_before_after.png` — bar chart: avg daily peak arrivals at each station
- `control_arrivals_trend.png` — daily arrivals over time with 7-day rolling average
- `control_monthly_trend.png` — monthly averages, M and R, with swap boundary marked
- `control_stations_report.txt` — plain-English findings

---

## `5_seasonality_analysis.py` — Ruling out winter as the cause

**What it does:** Directly addresses the question of whether January and February are simply worse months for subway service in general. It runs a three-way comparison at Roosevelt Island, on weekdays only:

| Period | Train | Season |
|---|---|---|
| Jan–Feb 2025 | F train | Winter (pre-swap) |
| Oct–Nov 2025 | F train | Autumn (pre-swap) |
| Jan–Feb 2026 | M train | Winter (post-swap) |

**The logic:** If seasonality were driving the difference, January–February 2025 (F train, winter) and October–November 2025 (F train, autumn) should differ materially — i.e., the two pre-swap periods should look as different as the pre/post-swap comparison. If the swap is the driver, the two pre-swap periods should look similar to each other, and only the post-swap winter should look dramatically different.

**Outputs** (saved to `results/seasonality/`):
- `seasonality_summary.csv` — Full statistics table across all three periods
- `seasonality_headways.png` — Three-period bar chart (the key visual for policymakers)
- `seasonality_hourly.png` — 24-hour headway profile with all three periods overlaid
- `seasonality_cdf.png` — Cumulative wait distribution showing the full distribution of waits
- `seasonality_report.txt` — Plain-English summary written for non-technical policymakers

**Run order:** Run `1_download.py`, then `1b_download_extended.py`, then `3_analyze.py`, then this script. It can also rebuild headways from `raw_data/` directly if needed.

---

## What this analysis can and cannot claim

**We can claim:** Observed train headways at Roosevelt Island were significantly longer in the post-swap period than the pre-swap period, across all daytime and evening time windows, in both directions, on weekdays.

**We can claim:** This change is consistent with the MTA's own acknowledgment that the M train runs less frequently than the F train it replaced.

**We can claim:** The increase substantially exceeds the MTA's written commitment to limit the impact to "approximately 1 minute on average."

**We cannot claim:** That the MTA deliberately misled anyone. The commitment was made in good faith based on planned service increases; we document that the planned increases were either not implemented or were insufficient.

**We cannot claim:** That ridership at Roosevelt Island has decreased as a result. We measure supply (how often trains came), not demand (how many people rode them).

**We cannot claim:** That the swap was the wrong decision for the broader system. The MTA's rationale — reducing merge conflicts at Queens Plaza to improve reliability for the E, F, M, and R lines — may well be valid. Our analysis is specifically about Roosevelt Island's experience, not a system-wide cost-benefit assessment.

---

## Reproducibility

Every number in our briefing materials can be reproduced from the scripts in this repository and the publicly available data on subwaydata.nyc. If you find an error, please open a GitHub issue. We will review it and correct the record if warranted.

The analysis was conducted in Python using pandas, numpy, and matplotlib. No proprietary tools or private datasets were used at any stage.

---

## Analytics & Privacy

The dashboard uses the standard analytics built into Streamlit Community Cloud. Google Analytics is not compatible with Streamlit, so we use Streamlit's built-in usage statistics instead.

### What Is Collected

Streamlit Community Cloud automatically tracks basic usage metrics (page views, active users) for apps deployed on the platform. No additional tracking code has been added to this app. No personally identifiable information is collected, no cookies are set, and no cross-site tracking occurs.

### How to Access Analytics

1. Go to the Streamlit Community Cloud dashboard
2. Select the app
3. Click **Analytics** in the app management panel

### For Users

No opt-out is required — the app sets no tracking cookies and collects no personal data beyond what Streamlit Community Cloud records by default for all hosted apps.
