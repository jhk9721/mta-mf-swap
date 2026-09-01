# mta-mf-swap

Measuring how often trains actually arrive at Roosevelt Island, before and after the MTA swapped the F train for the M.

**Data covers January 1, 2025 through September 1, 2026 — 177,559 train arrivals across 609 days.**

## Summary

On December 8, 2025, the MTA replaced the F train with the M train at Roosevelt Island on weekdays between 6:00 AM and 9:30 PM. In a Staff Summary dated September 15, 2025, the MTA wrote that added M service would hold the impact to "approximately 1 minute on average" of additional wait. This repository tests that commitment against the MTA's own data.

Trains now arrive less often in every weekday period, in both directions. In the evening rush toward Queens, the median gap between trains grew from 4.1 to 7.4 minutes, an increase of 80%. In the morning rush toward Manhattan, it grew from 4.8 to 7.6 minutes, an increase of 58%. The MTA converts headway to wait using average wait = headway ÷ 2. By that formula, the added wait across the four peak hour-and-direction combinations averages 1.45 minutes. All four exceed the 1-minute commitment. The largest, the evening ride home, is 1.65 minutes.

Peak train counts fell. Roosevelt Island received 9.2 northbound trains per hour during weekday rush hours before the swap and receives 6.5 now, a drop of 29%. Southbound fell from 10.2 to 6.8, a drop of 33%. These are counts of trains that stopped at the platform, not a derived statistic.

Three alternative explanations do not hold. Winter weather does not explain it: the weeks from the January 25 storm onward run 8.75 minutes against 8.92 minutes for the post-swap weeks before it. Season does not explain it: F service in January and February 2025 ran 6.58 minutes against 6.08 minutes in October and November 2025, a gap of half a minute, while the post-swap winter ran 9.00 minutes. A general decline in F service does not explain it: weekend F service at the same station, which the swap did not touch, improved from 10.8 to 9.2 minutes over the same period.

Service has improved modestly since the swap. Monthly peak medians fell from 8.02 minutes in December 2025 to 7.44 minutes in August 2026, a trend of −0.07 minutes per month (p = 0.079). Over the three most recent months the added wait is 1.33 minutes in the morning peak and 1.50 minutes in the evening peak. Both still exceed the commitment. At the observed rate of improvement, reaching 1 minute would take about four more years.

The MTA's own planning document, signed by the Chief of Operations Planning and approved to the MTA President, acknowledged before the swap that Roosevelt Island would face longer waits, and committed to added M service to limit the impact. Of the seven commitments this analysis can test, six fail and one is partially met.

Roosevelt Island has one subway station and no alternative line. Riders there cannot route around worse service.

The data, the code, and the methodology are all in this repository. A public dashboard lets anyone explore the same numbers.

# Methodology

This section states what we did, why we did it that way, and where the analysis is weak. Sections are ordered to match the scripts that produce each result.

---

## The core question

On December 8, 2025, the MTA replaced the F train with the M train at Roosevelt Island Station on weekdays, between 6:00 AM and 9:30 PM. The MTA claimed this would improve reliability for the broader system. We wanted to know what actually happened to wait times at Roosevelt Island.

We measured this using **headways** — the gap in minutes between one train arriving and the next. A headway of 5 minutes means trains are running every 5 minutes. If headways get longer after the swap, riders are waiting longer.

---

## Why we built this ourselves

The MTA publishes scheduled headways and departure times, meaning how often trains are *supposed* to run. Scheduled and actual times differ. Script 12 measures that gap directly at Roosevelt Island: the M runs 1.5 to 2 minutes behind its own peak schedule. We wanted what riders experienced on the platform, not what the MTA planned on paper.

That requires the MTA's real-time location data, archived over time.

---

## Data source

We used **[subwaydata.nyc](https://subwaydata.nyc)**, a website that archives the MTA's GTFS real-time feed every day. The GTFS (General Transit Feed Specification) real-time feed is the same data that powers apps like Google Maps and Citymapper — it's a continuous stream of train positions broadcast by the MTA itself.

subwaydata.nyc differs from most transit apps in **completeness**. Most apps poll the feed every few minutes and record what they see. subwaydata.nyc captures the full feed continuously. If a train arrives and departs between two polling checks, a polling-based archive misses it. This one does not. Missed arrivals would make headways look longer than they were, so completeness matters to a finding about headways growing.

---

## The comparison periods

**Post-swap** is December 8, 2025 onward. The swap took effect that morning, so the boundary is not a judgment call.

**Pre-swap** is every F-train weekday on record before December 8, 2025: January 1 through December 7, 2025, with no gaps. That is 243 weekdays against 192 post-swap weekdays.

We use the full pre-swap record rather than a selected window. A ten-week baseline would invite the obvious objection that we picked a flattering one. Using everything removes the choice.

It is also the conservative option, by a wide margin. F service in early and mid 2025 ran slightly worse than in autumn 2025, so including it raises the baseline and shrinks the measured change:

| Measure | Full pre-swap record (published) | Oct 1 – Dec 7, 2025 only |
|---|---|---|
| Weekdays in baseline | 243 | 48 |
| Evening rush, northbound | 4.12 → 7.42 min (**+80%**) | 3.75 → 7.42 min (+98%) |
| Morning rush, southbound | 4.83 → 7.63 min (**+58%**) | 4.53 → 7.63 min (+68%) |

We publish the smaller numbers. Anyone who prefers the narrower baseline can reproduce it by filtering `arrival_date >= 2025-10-01` before the split.

---

## `0_setup.py` — Environment verification

**What it does:** A pre-flight check that confirms a reviewer's machine is ready to run the rest of the pipeline before any data is downloaded. It verifies the Python version (≥ 3.9), checks that the required packages are installed at minimum versions (`requests`, `pandas`, `numpy`, `matplotlib`, `tqdm`), confirms at least 1 GB of free disk space, tests connectivity to subwaydata.nyc, and creates the `raw_data/` and `results/` output directories if they don't exist. Each check prints `[OK]`, `[WARN]`, or `[FAIL]`; the script exits non-zero if anything fails.

**Why this matters for reproducibility:** A reviewer who tries to reproduce our numbers shouldn't waste a 30-minute download discovering a missing package or a wrong Python version. Running `python3 0_setup.py` first surfaces those problems in seconds.

**Run order:** Run this once before anything else. Re-run only after changing Python environments.

---

## `1_download.py` — Pulling the raw data

**What it does:** Downloads compressed archives of MTA real-time data for every day in the study window: January 1, 2025 through today, resolved when the script runs. That spans the year-ago F train baseline, the eleven months of F service before the swap, December 2025 when the swap took effect on the 8th, and every month since. Each day is a separate compressed file of train location records. The full range is roughly 500 MB. Files already on disk are skipped, so a re-run fetches only what is new.

**Why these months:** We needed enough data before and after the swap to distinguish a real change from natural day-to-day variation. Ten weeks on each side gives us that statistical confidence. We started on October 1 rather than September 1 deliberately — September includes Labor Day and the tail end of summer schedules, which would add noise to the baseline. Starting in October gives us clean, settled weekday service.

**Why not go back further:** More history isn't always better. Going back a year would introduce seasonal variation (summer ridership, holiday schedules) that would confound the comparison. Our goal was a clean like-for-like: the same station, the same season, before and after one specific change.

---

## `1b_download_extended.py` — Extended download for seasonality testing

**What it does:** Downloads additional months of data not covered by `1_download.py`, serving two purposes: (1) provides a year-ago F train baseline (January–February 2025) to directly test whether winter seasonality — rather than the swap — explains the headway increase; and (2) fills any gaps left by `1_download.py` and extends the post-swap trend through the current date. Files already on disk are skipped automatically, so re-runs are safe.

**Why this matters:** A legitimate question raised after the initial analysis was whether January and February are simply worse months for subway service regardless of who's running the train. By downloading January–February 2025 data (F train, same season as the post-swap period), we can run a direct year-over-year comparison. If winter conditions were the main driver, the pre-swap winter (2025) and post-swap winter (2026) should look similar. They don't — which isolates the swap as the cause.

**Run order:** Run `1_download.py` first, then this script. All files land in the same `raw_data/` folder and are picked up automatically by the analysis scripts.

**Post-swap coverage:** The script no longer carries a hand-maintained month list. It walks the same window as `1_download.py` — January 1, 2025 through today — fetching anything missing and reporting the dates it could not get. To refresh the analysis later, just re-run it; the window extends itself. Days the source has not published yet are reported as unavailable rather than as errors.

**Estimated download:** ~250 days of data on a first run, roughly 250–500 MB. Allow 20–40 minutes depending on your connection.

---

## `1c_download_gtfs_static.py` — Downloading the MTA's published schedule

**What it does:** Downloads and unzips the MTA's public GTFS static feed (`google_transit.zip`) into `Resources/gtfs_static/`. This is the official, published *schedule* — what the MTA says trains are supposed to do — as distinct from the GTFS real-time feed used everywhere else in this analysis, which records what trains actually did. The script is idempotent: it skips the download if the expected files (`stops.txt`, `stop_times.txt`, `trips.txt`, `routes.txt`, `calendar.txt`, plus several others) are already present. Pass `--force` to re-download.

**Why we need both feeds:** The realized-headway analysis (scripts 3 through 11) uses only the real-time archive. Script 12 introduces a separate comparison — scheduled vs. realized — which requires the static schedule as its second input. Keeping the static download in its own script means reviewers who only want to verify the realized headway findings don't need to pull the schedule data.

**Run order:** Required before `12_schedule_vs_realized.py`. Otherwise standalone.

**Output:** `Resources/gtfs_static/` containing the canonical GTFS text files.

---

## `2_inspect.py` — Verifying we have the right data

**What it does:** Opens one of the downloaded files and prints its contents — column names, sample rows, and a search for Roosevelt Island records. It also specifically looks for what stop IDs appear in the data.

**Why this step matters:** This was where we discovered a critical issue. Our initial assumption was that Roosevelt Island's GTFS stop ID was **F09**. The inspect script showed that it was the wrong stop ID; the data uses **B06**. B06N for the northbound platform, B06S for the southbound platform.

We verified this against the official MTA Subway Stations and Complexes glossary published on data.ny.gov (re-checked July 2026). This step saved the entire analysis from being based on the wrong station. If we had filtered on F09, we would have had zero records and concluded there was no data — or worse, accidentally analyzed a different station.

**The lesson:** Never assume stop IDs. Always verify against the official source before doing any analysis.

---

## `3_analyze.py` — Computing the headways

This is the core of the analysis. It does several things in sequence.

### Loading and filtering to Roosevelt Island

The raw data contains every train at every station in the MTA system, hundreds of thousands of records per day. We filter to records where the stop ID is B06N or B06S, meaning Roosevelt Island only.

We do **not** filter by route here, and the distinction matters enough to state plainly. B06 is a single-service station. Whatever stops there is what a rider on the platform can board, so excluding a train that actually arrived would overstate wait times.

In practice 94.1% of records are F, FX, or M. The remaining 5.9% are E, R, and a handful of A, C, D, N, and Q arrivals: reroutes during planned track work, plus some feed labelling noise. Most fall on weekends and overnight. Dropping them moves the pre-swap weekday median from 6.28 to 6.30 minutes and the post-swap median from 8.75 to 8.83. Removing them would make the finding marginally stronger, so keeping them is the conservative choice.

Scripts 6, 7, and 8 do apply an explicit route filter, because those stations are served by multiple lines and the filter is necessary there.

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

The analysis includes the holiday period, December 22 through January 5. We considered excluding it, because lower holiday ridership might affect headways. Across the full post-swap record, those two weeks do not move the result: the peak-hour post-swap median is 7.92 minutes with them and 7.90 minutes without. We keep them in and report the figure that includes them.

### The January 25 storm

A significant winter storm hit New York on January 25, 2026. The MTA's anticipated defense is that the post-swap period was unusually bad because of weather. We tested this directly by stratifying weekday headways at Roosevelt Island into three periods:

| Period | n (headways) | Median headway | vs. pre-swap |
|---|---|---|---|
| Pre-swap (Oct 1 – Dec 7, 2025) | 17,527 | 6.08 min | — |
| Post-swap, before the storm (Dec 8 – Jan 24) | 9,579 | 8.92 min | **+47%** |
| Storm onward (Jan 25, 2026 – Sep 1, 2026) | 42,798 | 8.75 min | **+44%** |

The weeks from the storm onward are not worse than the post-swap weeks before it. They are 0.17 minutes better. That window now runs more than seven months and covers spring and summer, so it is no longer only a storm test. It is also a recovery test, and it shows that service after the storm did not return to pre-swap levels.

We report **+47%**, the pre-storm figure, as the headline, because it is measured before any weather event and cannot be attributed to one. The full post-swap record sits at **+44%**.

Numbers are recomputed end to end from `results/roosevelt_island_headways.csv`, filtered to weekdays and headways of 1 to 60 minutes, with no other filters. The exact filters are in `scripts/3_analyze.py`.

---

## `4_community_output.py` — Generating the charts

**What it does:** Takes `results/roosevelt_island_headways.csv`, the processed headway data produced by `3_analyze.py`, and produces eight charts and a set of talking points for community use. The current headways table covers January 1, 2025 through September 1, 2026 without gaps: a year-ago F-train baseline, the eleven months of F service before the swap, and every month since.

**Chart design decisions:**

We show the **median** as the primary bar, with a **90th percentile triangle** above it. The 90th percentile is the "worst 1-in-10" wait — the kind of delay that, while not typical, happens regularly enough that regular commuters will encounter it several times a month. Both statistics matter: the median tells you the typical experience, the 90th percentile tells you the risk exposure.

The **long-wait frequency charts** show the share of train intervals exceeding 5, 8, 10, 12, and 15 minutes. These state the finding in terms a rider can check against memory. Northbound during swap-active hours, the share of gaps over 10 minutes rose from 19% to 31%. In the evening rush specifically, it rose from 11% to 27%. Roughly one evening trip in four now carries a wait of more than 10 minutes, against one in nine before.

The **weekend charts** are the control. The swap is weekday-only, so the F train still serves Roosevelt Island on weekends in both periods. Weekend changes therefore cannot come from the swap. They show what happened to F service generally.

This answers the strongest counter-argument: that F service declined everywhere, and Roosevelt Island's weekday numbers are not about the swap at all. The data rejects it. Weekend daytime gaps fell from 10.8 to 9.2 minutes, an improvement of 15%, over the same months in which weekday gaps rose 58% to 80%. F service did not decline. Weekday service at this station did.

---

## `5_seasonality_analysis.py` — Ruling out winter as the cause

**What it does:** Directly addresses the question of whether January and February are simply worse months for subway service in general. It runs a three-way comparison at Roosevelt Island, on weekdays only:

| Period | Train | Season |
|---|---|---|
| Jan–Feb 2025 | F train | Winter (pre-swap) |
| Oct–Nov 2025 | F train | Autumn (pre-swap) |
| Jan–Feb 2026 | M train | Winter (post-swap) |

**The logic:** If season drives the difference, the two pre-swap periods should differ from each other about as much as pre differs from post. If the swap drives it, the two pre-swap periods should look alike and only the post-swap winter should stand apart.

The second is what the data shows. F service ran 6.58 minutes in January and February 2025 and 6.08 minutes in October and November 2025, a difference of 0.50 minutes. The post-swap winter ran 9.00 minutes, 2.42 minutes above the autumn F baseline. Season accounts for roughly a fifth of the gap. The swap accounts for the rest.

**Outputs** (saved to `results/seasonality/`):
- `seasonality_summary.csv` — Full statistics table across all three periods
- `seasonality_headways.png` — Three-period bar chart (the key visual for policymakers)
- `seasonality_hourly.png` — 24-hour headway profile with all three periods overlaid
- `seasonality_cdf.png` — Cumulative wait distribution showing the full distribution of waits
- `seasonality_report.txt` — Plain-English summary written for non-technical policymakers

**Run order:** Run `1_download.py`, then `1b_download_extended.py`, then `3_analyze.py`, then this script. It can also rebuild headways from `raw_data/` directly if needed.

---

## `6_analyze_63rd_st_line.py` — Confirming the degradation at all three stations

**What it does:** Extends the Roosevelt Island analysis to all three stations on the 63rd Street line — 21 St-Queensbridge (B04), Roosevelt Island (B06), and Lexington Av/63 St (B08) — and confirms that headway degradation is identical at all three. A route filter (F/FX pre-swap, M post-swap) is applied at every station to isolate the 63rd Street line service. This is especially important at B08, which is also served by the Q train; without the filter, Q arrivals would artificially compress measured headways there.

**Why this matters:** After applying the route filter, arrival counts at all three stations are within 1.5% of each other in every time bucket and direction (within 1% in four of six buckets; max spread 1.51% in evening rush southbound). Median headways vary by at most 0.1–0.2 minutes across stations — which is expected, since the same physical trains stop at B04, B06, and B08 sequentially with no branching. The three-station agreement is independent methodological validation: it rules out the possibility that Roosevelt Island's numbers are a station-specific data artifact. The degradation is a line-level service change.

**Run order:** Run `1_download.py` and `1b_download_extended.py` first. This script is otherwise standalone — it does not depend on `3_analyze.py`.

**Outputs** (saved to `results/63rd_st_line/`):
- `63rd_st_headways.csv` — headway records for all three stations
- `63rd_st_summary.csv` — median/p90 before vs. after by station
- `63rd_st_comparison_southbound.png`, `63rd_st_comparison_northbound.png` — side-by-side bar charts for each direction
- `63rd_st_daily_trend.png` — daily rolling median over time, all three stations overlaid
- `63rd_st_report.txt` — plain-English findings

---

## `7_analyze_m_train_frequency.py` — Measuring the MTA against its own wait-time commitment

**What it does:** Directly tests whether the MTA delivered on the wait-time commitment it made in its September 15, 2025 Staff Summary. The Staff Summary's verbatim commitment is that with added peak M service, *"the average additional wait time will be reduced to approximately 1 minute on average."* Using the MTA's own wait-time formula (average wait = headway ÷ 2), the script converts pre- and post-swap median headways at Roosevelt Island into average waits, computes the added wait above the F-train baseline, and compares it directly to the ~1-minute commitment. It also tracks whether the realized added wait has improved month by month since the swap.

**Why this matters:** The Staff Summary's only numeric commitment about Roosevelt Island riders is the 1-minute added-wait figure. We introduce no headway target the MTA did not state itself. Using the MTA's own arithmetic:

| Peak window | Pre-swap F | Post-swap M | Added wait |
|---|---|---|---|
| AM rush, southbound (toward Manhattan) | 4.83 min gap, 2.42 min wait | 7.63 min gap, 3.82 min wait | **+1.40 min** |
| AM rush, northbound (toward Queens) | 6.13 min gap, 3.07 min wait | 8.88 min gap, 4.44 min wait | **+1.37 min** |
| PM rush, northbound (toward Queens) | 4.12 min gap, 2.06 min wait | 7.42 min gap, 3.71 min wait | **+1.65 min** |
| PM rush, southbound (toward Manhattan) | 5.18 min gap, 2.59 min wait | 7.92 min gap, 3.96 min wait | **+1.37 min** |
| **Mean across the four peak cells** | | | **+1.45 min** |

All four exceed the commitment. The mean miss is 1.4 times the promise.

**On whether service is recovering:** it is, slowly. Monthly peak medians run 8.02, 8.25, 8.36, 7.67, 7.83, 8.23, 7.98, 7.70, and 7.44 minutes for December 2025 through August 2026. A linear fit gives −0.07 minutes per month (p = 0.079, r-squared = 0.38). The three most recent months average 7.71 minutes against 8.21 for the first three.

We state this rather than claim no improvement, because the MTA can compute the same trend and will. The improvement does not close the gap. Measured over June through August 2026 alone, the added wait is 1.33 minutes in the morning peak and 1.50 minutes in the evening peak. Both still exceed the commitment. At −0.07 minutes of headway per month, peak service reaches the promised 1 minute of added wait around mid-2030.

**Data source:** Uses `results/roosevelt_island_headways.csv` from `3_analyze.py` if available (faster). Falls back to rebuilding from raw archives if the CSV is not present.

**Run order:** Run `1_download.py`, `1b_download_extended.py`, and `3_analyze.py` first (or just the download scripts if the fallback path is acceptable).

**Outputs** (saved to `results/m_train_frequency/`):
- `m_train_trains_per_day.csv` — average daily train counts before/after, by direction and rush window
- `m_train_headway_stats.csv` — median/p90 headways with gap vs. MTA promise
- `m_train_monthly_trend.csv` — monthly breakdown of M headways since the swap
- `m_train_vs_commitment.png` — bar chart: pre-swap F average wait, post-swap M average wait, and the MTA's verbatim "~1 minute" added-wait commitment line
- `m_train_trend_over_time.png` — monthly median headway and average wait trend, with the pre-swap F baseline and the MTA's "~1 minute added wait" line marked
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

**What the data shows:** peak M arrivals at the three control stations rose from 79.1 to 82.1 trains per day per station, an increase of 3.8%. The MTA did add peak M service. The increase is too small to deliver the promised 1 minute of added wait at Roosevelt Island, where the realized added wait is 1.40 minutes in the morning peak and 1.65 minutes in the evening peak.

This is the one commitment the scorecard records as PARTIAL rather than FAIL. Stating it that way matters: the MTA kept part of this promise, and an analysis that scored it FAIL would be overreaching in a way a reviewer could check and reject.

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

## `11_did_control_stations.py` — Difference-in-differences against unaffected stations

**What it does:** Implements a formal difference-in-differences (DiD) test to close the MTA's anticipated defense that "the post-swap period was unusually bad because of winter storms and systemwide incidents, not the swap." The script compares the pre→post change in wait times at Roosevelt Island (the treated station) against the pre→post change at two control stations whose service was unaffected by the swap:

1. **7 train at Queensboro Plaza (718)** — a fully independent line on a different division (IRT vs. B division), different rolling stock, and a different signaling/control system. This is the strongest possible control for citywide weather or operational shocks.
2. **R train at Queens Plaza (G21)** — same Queens Blvd corridor as the affected M, but the R's route was unchanged through the swap. This captures any corridor-level weather, incident, or ridership effect that would have hit both the M and the R.

The DiD residual is the Roosevelt Island change *minus* the control change. If winter weather and systemwide incidents drove the post-swap numbers, the controls would inflate too and the residual would shrink toward zero. They don't — the residual remains large, which isolates the swap as the cause. Confidence intervals are produced by bootstrap resampling (1,000 iterations, fixed seed = 42 for exact reproducibility).

**Run order:** Run `3_analyze.py` and `8_analyze_queensboro_plaza.py` first; this script consumes their CSV outputs.

**Outputs** (saved to `results/did_control_stations/`):
- `did_summary.csv` — DiD point estimates and bootstrap confidence intervals for each control
- `did_monthly.csv` — monthly wait-time series per station
- `did_chart.png` — bar chart of treatment Δ vs. each control Δ vs. the DiD residual
- `did_monthly.png` — monthly trend lines, treatment overlaid against both controls
- `did_report.txt` — plain-English narrative

---

## `12_schedule_vs_realized.py` — Did the MTA even *schedule* the service it promised?

**What it does:** Compares the MTA's own published schedule (GTFS static) against what trains actually did (GTFS real-time) at Roosevelt Island. This separates two distinct failures: a planning failure (the schedule itself does not deliver on the commitment) and an operational failure (trains do not run on the schedule). The script runs two falsifiable comparisons:

1. **Post-swap weekday M trains** — scheduled peak headway vs. realized peak headway. If realized exceeds scheduled, that is a reliability gap that exists regardless of whether the underlying plan was sound.
2. **Post-swap weekend F trains** (methodology control) — weekend F service is unchanged by the swap, so any scheduled-vs-realized gap here represents the methodology's noise floor. It tells a reviewer how much GTFS-RT and GTFS static can differ even when nothing has changed.

The script also tests the September 2025 Staff Summary's specific written commitment that "peak-hour M service" would be increased so the average additional wait time would be "approximately 1 minute on average." Using the MTA's own wait-time methodology (average wait = headway ÷ 2), that promise translates to a scheduled peak headway no greater than ~7 minutes. We can test directly whether the schedule itself respects that commitment, independent of whether the trains hit the schedule.

**Run order:** Run `1c_download_gtfs_static.py` and `3_analyze.py` first.

**Outputs** (saved to `results/schedule_vs_realized/`):
- `schedule_vs_realized_hourly.csv` — per-hour scheduled vs. realized headway
- `schedule_vs_realized_buckets.csv` — per time-bucket comparison
- `schedule_vs_realized_chart.png` — line chart, weekday M
- `schedule_vs_realized_weekend.png` — weekend F methodology control
- `schedule_vs_realized_report.txt` — plain-English findings

---

## `13_journey_time_analysis.py` — End-to-end travel time for a Roosevelt Island rider

**What it does:** Moves beyond headways (how long you wait) to the rider's actual concern: total journey time (how long it takes to get to work). For a southbound Roosevelt Island commuter during weekday morning peak, the script computes end-to-end travel time to several representative Manhattan destinations — Lex Av/63 St, 57 St-6 Av, Rockefeller Center, Herald Sq, W 4 St, Broadway-Lafayette, 2 Av, and Delancey-Essex — before vs. after the swap.

**An important methodological clarification:** Despite the Staff Summary's phrasing, which implied the post-swap M would diverge from the 63rd Street line at 57 St, the post-swap weekday M in fact continues south on the 6 Ave Manhattan line all the way through Broadway-Lafayette before turning east to Brooklyn. Verified from GTFS static. This means Roosevelt Island riders going to most 6 Ave destinations have *direct* M service post-swap, just as they had direct F service pre-swap — the journey-time delta is driven by headway change, not by added transfers, at those stops. For destinations south of Broadway-Lafayette that are F-only (2 Av, Delancey-Essex), the script adds a transfer penalty at Broadway-Lafayette equal to half of the median post-swap F headway there (the MTA's own wait-time methodology).

For direct journeys, travel time is computed as the difference between arrival timestamps at origin and destination within the same trip_uid. Filters: weekday only, non-holiday, 6–9 AM peak.

**Run order:** Run `1_download.py` and `1b_download_extended.py` first. Standalone — reads raw archives directly.

**Outputs** (saved to `results/journey_times/`):
- `journey_times.csv` — one row per origin-destination × period × journey type
- `journey_times.png` — bar chart, Δ travel time per destination
- `journey_times_report.txt` — plain-English findings

---

## `14_commitment_scorecard.py` — Single-page verdict against each written promise

**What it does:** Consolidates findings from scripts 3, 7, 8, 9, 11, and 12 into a single one-page scorecard, organized around the specific falsifiable commitments the MTA made in its September 15, 2025 Staff Summary and its April 23, 2026 letter. For each commitment, the scorecard quotes the MTA's own language, reports the measured value from our data, and assigns one of five verdicts:

- **PASS** — commitment met
- **FAIL** — commitment broken (with the magnitude of the miss)
- **PARTIAL** — qualified support
- **UNTESTED** — analysis not yet performed
- **UNKNOWN** — required input CSV is missing; re-run the upstream script

This script performs *no new analysis*. It only reads and synthesizes the CSV outputs produced by earlier scripts. That separation is deliberate: a reviewer who is skeptical of any single verdict can trace it back to the exact CSV row and the exact script that produced it. If a CSV is missing, the script flags it as `UNKNOWN` rather than fabricating a result.

**Current results** (data through September 1, 2026, from `dashboard/data/commitment_scorecard.csv`):

| # | Commitment | Verdict |
|---|---|---|
| 1 | Roosevelt Island rider wait time | **FAIL** |
| 2 | Average added wait at Roosevelt Island (verbatim commitment) | **FAIL** |
| 3 | Systemwide peak M-train service increase | PARTIAL |
| 4 | Queens Plaza rush-hour reliability (the central justification) | **FAIL** |
| 5 | Scheduled peak headway of 7 minutes or less | **FAIL** |
| 6 | Operational delivery against the MTA's own schedule | **FAIL** |
| 7 | Queens Blvd rider travel-time savings | **FAIL** |

Six of seven fail. The one PARTIAL is the systemwide M service increase: the MTA added peak M trains, but not enough to deliver the wait time it committed to.

Commitments 5 and 6 separate two distinct failures. Commitment 5 asks whether the published schedule could have delivered the promise. Commitment 6 asks whether trains ran to that schedule. Both fail, which means the plan was insufficient *and* operations fell short of the plan.

**Run order:** Run as the final step, after all upstream analysis scripts have produced their CSVs.

**Outputs** (saved to `results/`):
- `commitment_scorecard.txt` — narrative, one section per commitment
- `commitment_scorecard.csv` — tabular, one row per commitment for easy reference

---

## What this analysis can and cannot claim

**We can claim:** Trains arrived less often at Roosevelt Island after the swap than before it, in every daytime and evening window, in both directions, on weekdays. The weekday median gap grew 2.47 minutes, with a bootstrap 95% confidence interval of 2.42 to 2.57 minutes.

**We can claim:** Fewer trains stop at the station during peak hours. Northbound fell from 9.2 to 6.5 per hour, southbound from 10.2 to 6.8.

**We can claim:** The added wait exceeds the MTA's written commitment of "approximately 1 minute on average" in all four peak hour-and-direction combinations, and still exceeds it in the three most recent months.

**We can claim:** Weather, season, and a general decline in F service do not account for the change. Each has a control in this repository, and each control comes back flat or improving.

**We cannot claim:** That the MTA misled anyone. The commitment rested on planned service increases. We document that those increases were smaller than the commitment required. Script 9 finds peak M arrivals at control stations rose 3.8%, so service was added, just not enough.

**We cannot claim:** That ridership at Roosevelt Island fell. We measure supply, meaning how often trains came. We do not measure demand.

**We cannot claim:** That the swap was wrong for the system as a whole. The MTA's rationale was to reduce merge conflicts at Queens Plaza and improve reliability for the E, F, M, and R lines. Script 8 tests the Queens Plaza claim and does not find the promised improvement, but a full system cost-benefit assessment is outside what this data supports. This analysis is about one station.

**We cannot claim:** Anything about service after September 1, 2026. See "Keeping the analysis current" below.

---

## Keeping the analysis current

**The data in this repository ends September 1, 2026.** Every number above is computed from that window.

This matters most for claims about recovery. We can show what service did through September 1, 2026. We can show nothing after it. A finding that service has not reached the MTA's commitment goes stale the moment the MTA changes a schedule, and the MTA revises schedules several times a year.

Re-run the pipeline before presenting any of these numbers:

```
cd scripts
python3 0_setup.py                    # checks Python, packages, disk, connectivity
python3 1b_download_extended.py       # extends to today; skips files already on disk
python3 3_analyze.py                  # rebuilds the headway table
python3 14_commitment_scorecard.py    # after scripts 7, 8, 9, 11, 12, 13
```

`1b_download_extended.py` ends its range at `date.today()`, so the window extends itself on each run. Nothing needs editing to bring the analysis forward. To see what a run will fetch before committing to the download, check the date range it prints at startup.

To refresh the dashboard, copy the regenerated `results/roosevelt_island_headways.csv` over `dashboard/roosevelt_island_headways.csv.gz` (gzipped). Every figure on the dashboard is computed from that file at render time, so the site updates itself once the data does.

---

## Reproducibility

Every number in this repository can be reproduced from these scripts and from data published at subwaydata.nyc. If you find an error, open a GitHub issue. We will check it and correct the record if it is right.

The analysis runs in Python using pandas, numpy, and matplotlib. It uses no proprietary tools and no private datasets.

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
