# Demand-Supply Gap Analysis
## Ayushman Bharat PM-JAY — Uttar Pradesh
### Synthetic Data Analysis Report

---

## Executive Summary

This analysis uses three years of synthetic AB PM-JAY data from Uttar Pradesh to examine where demand for care is not being matched by local supply. It covers 641 blocks, 75 districts, about 50,000 households and 22,500 claims, and is designed to identify the main geographic and service-level barriers facing beneficiaries. The purpose is to move beyond overall scheme coverage and show where access breaks down in practice, so that state and district planning can better align empanelment, referral pathways and outreach with actual patient need.

The findings point to a severe spatial mismatch between beneficiary demand and available services. More than one-third of blocks have no empanelled hospital at all, and very few patients are treated close to home, with almost no care retained within the same block and only limited retention within the same district. The analysis also identifies thousands of block-specialty gaps where demand exists but no local provider offers the required service, alongside a meaningful financial loss from avoidable out-of-area care. Utilization remains low overall despite high card activation, suggesting that activation alone is not translating into effective access, especially in blocks with seasonal demand spikes and in places where the only hospital has exited the scheme.

These patterns have clear operational implications for AB PM-JAY in Uttar Pradesh. First, empanelment needs to be more geographically targeted, with priority given to uncovered blocks, single-provider blocks and specialty shortages that force patients to travel. Second, the state should treat card activation, referral support and hospital availability as linked parts of the same access chain, because high activation without local supply still leaves beneficiaries unable to use the scheme. Third, planning should be seasonal and district-specific, with pre-emptive capacity measures before the August–September surge and stronger monitoring of delisting risk, so that service interruptions do not deepen existing inequities or increase avoidable spending.

---

## Dataset Overview

| Parameter | Value |
|-----------|-------|
| Geographic scope | Uttar Pradesh — 18 divisions, 75 districts, 641 blocks |
| Observation period | January 2022 – December 2025 (36 months) |
| Households enrolled | 50,000 |
| Beneficiaries | ~205,847 |
| Empanelled hospitals | 800 |
| Cases analysed | 22,500 |
| Parquet analytics files | 10 |

---

## 1. Access and Utilization Gaps

**Policy question:** Which blocks have high enrolment but low utilization, suggesting access barriers rather than low need?

The pattern points to a clear access problem rather than weak demand. A substantial share of blocks have no empanelled hospital at all, and many others depend on a single facility, which limits choice, increases travel time, and can suppress use even where enrolment is high. The high-enrolment, low-utilization blocks are concentrated in both urban and peri-urban settings such as Lucknow and Varanasi, suggesting that enrolment alone is not translating into effective service access; beneficiaries may be facing referral delays, provider congestion, out-of-pocket costs, or poor awareness of where to go for care.

The most concerning blocks are those with very low utilization combined with little or no local hospital presence, because they likely reflect structural access barriers rather than temporary underuse. In these places, low service uptake is consistent with long travel distances, weak provider availability, and limited continuity of care, especially where only one hospital serves the block or none is available locally. Overall, the findings suggest that improving utilization will require expanding empanelment in underserved blocks, reducing dependence on single facilities, and strengthening navigation support so enrolled households can actually reach care.

### Key Metrics

| Metric | Value |
|--------|-------|
| Blocks with zero empanelled hospitals | 206 (32.1%) |
| Blocks with single-hospital dependency | 212 (33.1%) |
| State-wide utilization rate | 10.4% |
| High-enrolment low-utilization blocks | 75 |
| High-demand low-local-supply blocks | 30 |

### Top 10 High-Enrolment Low-Utilization Blocks

| block | district | total_beneficiaries_enrolled | overall_utilization_rate | total_hospitals | zero_supply |
| --- | --- | --- | --- | --- | --- |
| Mohanlalganj | Lucknow | 652 | 0.084 | 3.000 | False |
| Chinhat | Lucknow | 599 | 0.083 | 2.000 | False |
| Baragaon | Varanasi | 575 | 0.083 | 2.000 | False |
| Chiraigaon | Varanasi | 556 | 0.083 | 3.000 | False |
| Sarbanandapur | Kanpur Nagar | 554 | 0.081 | 1.000 | False |
| Lakhimpur Block 1 | Lakhimpur Kheri | 516 | 0.072 | — | True |
| Bahraich Block 7 | Bahraich | 514 | 0.076 | — | True |
| Bulandshahr Block 3 | Bulandshahr | 513 | 0.090 | 1.000 | False |
| Moradabad Block 7 | Moradabad | 512 | 0.088 | 1.000 | False |
| Bijnor Block 3 | Bijnor | 505 | 0.087 | 1.000 | False |

---

## 2. Specialty Supply Gaps

**Policy question:** Which block × specialty combinations have patient demand but no local hospital offering that specialty?

The matrix shows a substantial access problem: many block-specialty combinations have patients seeking care but no hospital offering that specialty locally. The largest unmet need is concentrated in core, high-volume specialties such as obstetrics and gynaecology, general surgery, medicine, orthopaedics, cardiology and urology, which points to gaps in essential secondary care rather than only in niche services. This pattern is especially concerning because these are the services most likely to drive avoidable delays, referrals, and out-of-pocket spending when patients must travel outside their block.

The highest-volume gaps are spread across multiple districts and often appear in blocks where the nearest alternative is still within the same district, suggesting that “some supply nearby” does not necessarily translate into timely or usable access. For AB PM-JAY in Uttar Pradesh, this implies that the main barrier is not just district-level availability but the absence of specialty coverage at the block level, especially for time-sensitive and high-demand services. The estimated revenue leakage from no-supply gaps also indicates that these are not marginal misses: they represent a meaningful volume of foregone care that could be captured through targeted empanelment, outreach, or referral-network strengthening in the worst-served blocks.

### Revenue Leakage by Specialty (NO_SUPPLY gaps)

| specialty_code | specialty_name | no_supply_blocks | total_unmet_cases | revenue_leakage |
| --- | --- | --- | --- | --- |
| CARD | Cardiology | 202 | 791.000 | 1222.5 L |
| ORTH | Orthopaedics | 206 | 804.000 | 769.0 L |
| OBG | Obstetrics & Gynaecology | 202 | 1010.000 | 237.5 L |
| GS | General Surgery | 200 | 999.000 | 204.3 L |
| URO | Urology | 241 | 711.000 | 195.4 L |
| ONCO | Oncology | 210 | 406.000 | 133.2 L |
| PEDS | Paediatrics | 239 | 466.000 | 110.5 L |
| OPTH | Ophthalmology | 202 | 567.000 | 98.5 L |
| MED | General Medicine | 201 | 805.000 | 97.0 L |
| NEURO | Neurology | 186 | 339.000 | 87.8 L |
| ENT | ENT | 207 | 381.000 | 50.8 L |

### Top 15 Block × Specialty Gaps by Unmet Case Volume

| block | district | specialty_code | specialty_name | cases_demanding | gap_severity | nearest_block_with_supply |
| --- | --- | --- | --- | --- | --- | --- |
| Khair | Aligarh | OBG | Obstetrics & Gynaecology | 15.000 | NO_SUPPLY | Atrauli |
| Sitapur Block 6 | Sitapur | GS | General Surgery | 15.000 | NO_SUPPLY | Sitapur Block 1 |
| Mehnagar | Azamgarh | MED | General Medicine | 14.000 | NO_SUPPLY | Ateha |
| Simbhawali | Ghaziabad | OBG | Obstetrics & Gynaecology | 14.000 | NO_SUPPLY | Bhojpur |
| Jaunpur Block 3 | Jaunpur | GS | General Surgery | 13.000 | NO_SUPPLY | Jaunpur Block 1 |
| Kakori | Lucknow | GS | General Surgery | 13.000 | NO_SUPPLY | Bakshi Ka Talab |
| Jaunpur Block 6 | Jaunpur | CARD | Cardiology | 12.000 | NO_SUPPLY | Jaunpur Block 1 |
| Kakori | Lucknow | OBG | Obstetrics & Gynaecology | 12.000 | NO_SUPPLY | Bakshi Ka Talab |
| Kakori | Lucknow | ORTH | Orthopaedics | 12.000 | NO_SUPPLY | Bakshi Ka Talab |
| Meja | Prayagraj | CARD | Cardiology | 12.000 | NO_SUPPLY | Bahria |

---

## 3. Disease Burden vs. Infrastructure

**Policy question:** Does the disease mix in each block match the infrastructure available at local hospitals?

The disease mix does not align well with available infrastructure in many blocks, and the gap is large enough to affect access in routine care as well as referral pathways. The biggest pressure is coming from non-communicable diseases, but the mismatch is also substantial for injuries, maternal and neonatal care, surgical needs, and communicable diseases, showing that the problem is not confined to one service line. In policy terms, this suggests that block-level capacity is not keeping pace with the actual case profile, so patients are likely facing delays, avoidable travel, or out-of-pocket referrals when the needed facility type is missing locally.

The most concerning pattern is that the highest-volume mismatches are concentrated in a few blocks where common and time-sensitive conditions are appearing without the right infrastructure nearby. This is especially worrying for maternal-neonatal and communicable disease cases, where delays can quickly worsen outcomes, and for NCDs, where repeated access barriers can push patients toward late presentation and higher-cost care. Overall, the findings point to a spatial mismatch between burden and readiness, implying that planning should prioritize block-level facility upgrades, stronger referral links, and targeted service expansion in the most strained areas.

### Infrastructure Mismatches by Disease Category

| Disease Category | Blocks with Mismatch | Required Facility |
|-----------------|---------------------|-------------------|
| NCD | 358 | ICU with AC or HDU |
| SURGICAL | 233 | Fully equipped OT |
| INJURY | 274 | Casualty AND OT |
| MATERNAL_NEONATAL | 272 | Labour room |
| COMMUNICABLE | 216 | General ward or Casualty |
| OTHER | 214 | General ward |

### Top 12 Blocks with Infrastructure Mismatch

| block | district | disease_category | case_count | hospitals_with_required_facilities | infrastructure_strain |
| --- | --- | --- | --- | --- | --- |
| Kakori | Lucknow | COMMUNICABLE | 22 | 0.000 | — |
| Kakori | Lucknow | MATERNAL_NEONATAL | 21 | 0.000 | — |
| Meja | Prayagraj | COMMUNICABLE | 20 | 0.000 | — |
| Sitapur Block 6 | Sitapur | OTHER | 20 | 0.000 | — |
| Rohania | Varanasi | NCD | 20 | 0.000 | — |
| Maharajganj Block 7 | Maharajganj | COMMUNICABLE | 19 | 0.000 | — |
| Jaunpur Block 3 | Jaunpur | COMMUNICABLE | 19 | 0.000 | — |
| Jaunpur Block 3 | Jaunpur | OTHER | 18 | 0.000 | — |
| Lakhimpur Block 2 | Lakhimpur Kheri | COMMUNICABLE | 17 | 0.000 | — |
| Kakori | Lucknow | OTHER | 17 | 0.000 | — |
| Tappal | Aligarh | COMMUNICABLE | 17 | 0.000 | — |
| Simbhawali | Ghaziabad | OTHER | 17 | 0.000 | — |

---

## 4. Patient Flow and Portability

**Policy question:** Where are beneficiaries going for care? What does the flow pattern reveal about local gaps?

The flow pattern shows very weak local care use and heavy dependence on facilities outside the beneficiary’s immediate area. Very few cases are handled within the same block or even the same district, which suggests that nearby public or empanelled private capacity is either unavailable, not trusted, or not functioning well enough to meet demand. The blocks with the highest leakage are almost entirely sending patients out of district, pointing to a structural gap in local service availability rather than a small number of isolated referrals. Out-of-state portability is present but limited, so the main problem is not interstate migration; it is the inability of many beneficiaries to find usable care close to home.

The district-level balance reinforces this picture. A small set of districts is drawing in more patients than it sends out, which likely reflects stronger hospital availability, better perceived quality, or easier access to specialist services in those locations. By contrast, several districts are consistently losing patients, indicating that residents are bypassing local facilities and travelling elsewhere for even routine PM-JAY care. For policy, this pattern points to access barriers such as weak provider density, poor service readiness, and low confidence in local facilities, especially in districts with persistent outflows.

### Flow Distribution (State-wide)

| Flow Category | Cases | Share |
|---------------|-------|-------|
| Same block | 44 | 0.2% |
| Same district, different block | 308 | 1.4% |
| Different district, same division | 21309 | 94.7% |
| Out of state (portability) | 839 | 3.7% |

### Top 12 Highest-Leakage Blocks

| block | district | total_cases | cases_same_block | cases_diff_district | cases_out_of_state | leakage_rate |
| --- | --- | --- | --- | --- | --- | --- |
| Akola | Agra | 22 | 0 | 22 | 0 | 1.000 |
| Ambedkar Block 1 | Ambedkar Nagar | 35 | 0 | 35 | 0 | 1.000 |
| Ambedkar Block 2 | Ambedkar Nagar | 21 | 0 | 21 | 0 | 1.000 |
| Ambedkar Block 3 | Ambedkar Nagar | 31 | 0 | 31 | 0 | 1.000 |
| Ambedkar Block 4 | Ambedkar Nagar | 22 | 0 | 21 | 1 | 1.000 |
| Ambedkar Block 5 | Ambedkar Nagar | 33 | 0 | 31 | 2 | 1.000 |
| Ambedkar Block 6 | Ambedkar Nagar | 29 | 0 | 29 | 0 | 1.000 |
| Amethi Block 3 | Amethi | 26 | 0 | 24 | 2 | 1.000 |
| Amethi Block 4 | Amethi | 28 | 0 | 27 | 1 | 1.000 |
| Amethi Block 5 | Amethi | 30 | 0 | 30 | 0 | 1.000 |

### District Net Patient Flow (Importers vs Exporters)

| district | net_flow |
| --- | --- |
| Gorakhpur | 316 |
| Lucknow | 171 |
| Hardoi | 152 |
| Hathras | 147 |
| Gautam Buddha Nagar | 131 |
| Basti | 108 |
| Mau | 107 |
| Ballia | 103 |
| Rampur | 92 |
| Kaushambi | 92 |
| Meerut | 91 |
| Mainpuri | 84 |
| Jhansi | 83 |
| Kasganj | 79 |
| Banda | 71 |
| Varanasi | 62 |
| Mirzapur | 61 |
| Badaun | 56 |
| Auraiya | 54 |
| Kannauj | 49 |

---

## 5. Enrolment-to-Card Activation Drop-off

**Policy question:** Are there blocks where beneficiaries enrol but fail to receive an active Ayushman Card?

Yes. The data show a clear enrolment-to-card activation gap in a sizeable set of blocks, with many performing well below the state average. The most concerning cases are those where activation is weak and rejection is also elevated, because this suggests that beneficiaries are not just delayed but are being screened out or unable to complete the process. Blocks such as Sambhal, Chhata, Ambedkar Nagar, and Faridpur stand out as priority areas for investigation because their drop-off is materially worse than the state norm and appears to reflect real access or verification barriers rather than random fluctuation.

The pattern also suggests that the problem is not uniform: some blocks have high drop-off alongside rejection rates above the state average, while others have moderate rejection but still lose a large share of enrollees before card activation. This points to a mix of bottlenecks, including documentation issues, operator or portal-level processing problems, and possible beneficiary-side barriers such as travel, follow-up, or awareness. For policy action, these blocks should be treated as service delivery hotspots where process audits, grievance review, and on-site support could quickly improve conversion from enrolment to active coverage.

### Drop-off Summary

| Metric | Value |
|--------|-------|
| State-wide card activation rate | 87.4% |
| Blocks above 75th percentile drop-off | 160 |
| State-wide enrolment rejection rate | 14.5% |
| Beneficiaries without any card | 10,228 |
| Beneficiaries with inactive/disabled card | 15,731 |

### Top 12 High Drop-off Blocks

| block | district | total_beneficiaries | card_activation_rate | drop_off_rate | enrolment_rejection_rate |
| --- | --- | --- | --- | --- | --- |
| Sambhal Block 6 | Sambhal | 211 | 0.787 | 0.213 | 0.180 |
| Chhata | Mathura | 291 | 0.804 | 0.196 | 0.182 |
| Ambedkar Block 4 | Ambedkar Nagar | 244 | 0.807 | 0.193 | 0.193 |
| Sant Block 3 | Sant Kabir Nagar | 233 | 0.815 | 0.185 | 0.116 |
| Chandauli Block 2 | Chandauli | 246 | 0.817 | 0.183 | 0.163 |
| Sant Block 2 | Sant Ravidas Nagar | 181 | 0.818 | 0.182 | 0.149 |
| Faridpur | Bareilly | 291 | 0.818 | 0.182 | 0.196 |
| Shamli Block 4 | Shamli | 158 | 0.823 | 0.177 | 0.215 |
| Hapur Block 5 | Hapur | 232 | 0.828 | 0.172 | 0.164 |
| Sant Block 1 | Sant Ravidas Nagar | 198 | 0.828 | 0.172 | 0.111 |

---

## 6. Repeat Utilization Patterns

**Policy question:** Which blocks have high repeat admissions, potentially signalling chronic disease burden or ineffective initial treatment?

Repeat use of AB PM-JAY services is concentrated in a relatively large set of blocks, but the pattern is uneven and mostly modest in scale. The highest-repeat blocks are small in absolute caseload, so their elevated rates should be read as signals of local clustering rather than proof of system-wide failure. Still, the concentration of high-repeat blocks across districts such as Hamirpur, Shamli, Meerut, Chandauli, Mathura, Jalaun, Mahoba, Banda and Shravasti suggests that some areas may have a heavier chronic disease burden, weaker continuity of care, or both.

What is more reassuring is that no block shows evidence of repeat use consistent with treatment failure, which argues against widespread poor-quality care as the main driver. The more likely explanation is access friction: patients may be returning because they cannot complete treatment in one episode, face referral gaps, or need follow-up for conditions that are not well managed at the first point of care. Policy attention should therefore focus on these high-repeat blocks as candidates for stronger primary care linkage, better discharge and referral coordination, and closer review of whether repeated claims reflect unresolved illness rather than avoidable re-visits.

### Repeat Utilization Summary

| Metric | Value |
|--------|-------|
| State-wide repeat utilization rate | 5.2% |
| Blocks with high repeat rate (>75th pct) | 155 |
| Blocks flagged for treatment failure | 0 |
| Total same-procedure same-hospital repeat pairs | 0 |
| Total same-procedure different-hospital pairs | 43 |

---

## 7. Seasonal Demand Patterns

**Policy question:** Do certain blocks experience seasonal demand surges that may overwhelm local capacity?

Seasonal surges are widespread rather than isolated, with nearly all blocks that meet the activity threshold showing at least one month of elevated demand. The timing is concentrated in the monsoon and post-monsoon period, with a smaller but still important spike in spring, which suggests that local capacity is being stressed by predictable, recurring demand rather than random variation. The fact that surge months are most often driven by “other” conditions, but also frequently by NCD, communicable, maternal-neonatal, and surgical care, points to a broad service mix being affected, not a single programme area.

The most seasonal blocks show large swings between low and high months, which is a warning sign for access barriers when patients need care most. In several blocks, communicable disease dominates the peak months, consistent with weather-linked outbreaks and delayed care-seeking, while others peak in NCD or maternal-neonatal care, suggesting that routine follow-up and timely referral may be disrupted by distance, transport, or weak local service availability. For policy, this means capacity planning should be seasonal and block-specific, with extra attention to monsoon preparedness, referral coordination, and temporary load balancing in the most volatile blocks.

### Seasonality Summary

| Metric | Value |
|--------|-------|
| Blocks meeting analysis threshold | 626 of 641 |
| Blocks with at least one surge month | 620 (96.7%) |
| Peak calendar months | August (month 8), July (month 7), September (month 9) |
| Dominant surge disease | Communicable diseases |

### Most Seasonal Blocks (by Coefficient of Variation)

| block | district | seasonality_index | peak_to_trough_ratio | peak_months | peak_disease_category |
| --- | --- | --- | --- | --- | --- |
| Auraiya Block 4 | Auraiya | 2.308 | 4.000 | 1,2,4 | COMMUNICABLE |
| Kasganj Block 8 | Kasganj | 2.114 | 5.000 | 4,12 | NCD |
| Kasganj Block 7 | Kasganj | 1.890 | 3.000 | 10,11 | COMMUNICABLE |
| Banda Block 6 | Banda | 1.782 | 4.000 | 1,4,9 | COMMUNICABLE |
| Mahoba Block 5 | Mahoba | 1.769 | 3.000 | 3,8 | OTHER |
| Mahoba Block 8 | Mahoba | 1.757 | 2.000 | 7,8 | COMMUNICABLE |
| Shravasti Block 7 | Shravasti | 1.757 | 3.000 | 6,8,10 | MATERNAL_NEONATAL |
| Sant Block 1 | Sant Kabir Nagar | 1.757 | 3.000 | 8,9 | OTHER |
| Mainpuri Block 1 | Mainpuri | 1.716 | 4.000 | 10,11 | MATERNAL_NEONATAL |
| Mainpuri Block 6 | Mainpuri | 1.680 | 4.000 | 2,5,8 | NCD |
| Chitrakoot Block 8 | Chitrakoot | 1.663 | 3.000 | 2,3,6,8,9 | COMMUNICABLE |
| Shravasti Block 3 | Shravasti | 1.663 | 3.000 | 8,9,10 | COMMUNICABLE |

---

## 8. Delisted Hospital Impact

**Policy question:** Which blocks have lost effective hospital capacity due to scheme delisting?

The delisting has not just removed individual facilities; in a small set of blocks it has effectively wiped out local scheme-based hospital access. The most serious cases are the sole-provider blocks, where patients now have no remaining PM-JAY hospital in the block and must travel elsewhere for care. A further set of blocks has lost most of its bed capacity, which means that even where some hospitals remain, the local system is much thinner and more vulnerable to crowding, delays, and referral bottlenecks.

The access risk is especially high where delisted hospitals also carried unique specialties, because the loss is not only about beds but about specific services such as surgery, obstetrics, paediatrics, orthopaedics, and advanced medical care. In these blocks, patients may face longer travel times, higher out-of-pocket costs, and delayed treatment for time-sensitive conditions. The pattern suggests that delisting decisions should be assessed block by block, with priority given to restoring capacity or arranging substitute empanelment in places where the scheme has created a service vacuum.

### Delisted Hospital Detail

| hospital_name | block | district | delisted_beds | bed_share_lost | sole_provider_delisted | specialties_lost | block_cases_per_remaining_bed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Primary Health Centre Gonda Block 6 | Gonda Block 6 | Gonda | 129 | 1.000 | True | CARD,ENT,GS,MED,NEPHRO,NEURO,OBG,OPTH,ORTH,URO | — |
| Medical College Hospital Amroha | Amroha Block 2 | Amroha | 32 | 0.169 | False | CARD,DERM,ENT,GS,MED,NEPHRO,NEURO,OBG,OPTH,ORTH,PEDS,URO | 0.159 |
| Dr. Sharma Orthopaedic Centre | Pratapgarh Block 6 | Pratapgarh | 165 | 0.357 | False |  | 0.084 |
| Trauma Centre Auraiya Block 2 | Auraiya Block 2 | Auraiya | 27 | 0.098 | False | OPTH | 0.032 |
| District Hospital Bijnor | Bijnor Block 7 | Bijnor | 6 | 0.046 | False |  | 0.460 |
| Gupta & Agarwal Multispeciality Hospital | Saharanpur Block 4 | Saharanpur | 33 | 0.287 | False |  | 0.622 |
| Women Hospital Farrukhabad | Farrukhabad Block 8 | Farrukhabad | 269 | 1.000 | True | CARD,GS,MED,NEURO,OBG,OPTH,ORTH,PEDS,URO | — |
| Laxmi Children Hospital | Jungle Kaudiram | Gorakhpur | 47 | 0.196 | False |  | 0.150 |
| Trauma Centre Kushinagar Block 2 | Kushinagar Block 2 | Kushinagar | 75 | 0.682 | False | PEDS,URO | 0.571 |
| Dr. Verma Nursing Home | Bilhaur | Kanpur Nagar | 59 | 1.000 | True | CARD,ENT,GS,MED,NEURO,OBG,ONCO,OPTH,ORTH,PEDS | — |

---

## 9. Policy Recommendations

1. Prioritise hospital empanelment and service expansion in zero-hospital and single-provider blocks, with a fast-track package for high-burden areas. The analysis shows that 206 blocks have no hospitals and another 212 depend on a single hospital, creating extreme access risk and avoidable travel for patients. The State Health Agency should lead this with district health officers identifying priority blocks and the NHA supporting rapid empanelment and compliance clearance.

2. Build specialty capacity where leakage is highest, especially in OBG, GS, MED, ORTH and CARD. These five specialties account for the largest demand-supply gaps and are linked to an estimated INR 35.3 Cr in leakage, showing that patients are being pushed outside the local system for care that should be available closer to home. The SHA should set district-wise specialty targets, while district health officers should work with hospitals to recruit, contract, or refer-in specialists; NHA should support package rationalisation and empanelment norms.

3. Strengthen district-level retention by creating referral and care pathways that keep patients within their home district whenever clinically appropriate. Only 1.6% of patients are retained locally, which means the system is heavily dependent on cross-district movement and is likely increasing costs, delays, and fragmentation of care. The SHA should issue retention targets and referral protocols, district health officers should monitor patient flows, and NHA should enable data dashboards to track cross-district leakage.

4. Align infrastructure planning with actual disease burden, especially for NCD, surgical, and maternal care. The analysis shows that 1,567 blocks do not have infrastructure matched to their local burden, so capacity is not where demand is concentrated. The SHA should use block-level burden maps to guide new investments, district health officers should validate local gaps, and NHA should support planning standards and capital prioritisation.

5. Improve enrolment and card activation in blocks with high drop-off, with focused outreach and last-mile support. In 160 blocks, enrolment falls off above the state average and card activation remains incomplete, which weakens effective coverage even where eligibility exists. The SHA should run targeted activation drives, district health officers should coordinate camps and follow-up, and NHA should strengthen digital workflows and beneficiary communication.

6. Prepare seasonal surge response plans and protect service continuity in vulnerable blocks. The August–September spike in 620 blocks, driven mainly by communicable diseases, shows that demand is predictable and should be managed before it overwhelms facilities. The SHA should issue surge preparedness guidance, district health officers should pre-position staff and medicines, and NHA should ensure claims and package rules do not delay care during peak periods.

---

## Appendix: Files Generated

| File | Description | Rows |
|------|-------------|------|
| `gap_utilization_scores.parquet` | Block-level utilization gap scoring | 641 |
| `gap_specialty_matrix.parquet` | Block × specialty supply gap matrix | 7,138 |
| `gap_disease_burden.parquet` | Disease burden vs infrastructure mismatch | 3,717 |
| `gap_portability_flows.parquet` | Block-level patient retention/leakage | 641 |
| `gap_district_patient_flows.parquet` | District-to-district flow matrix | 5,080 |
| `gap_card_dropoff.parquet` | Enrolment-to-card activation analysis | 641 |
| `gap_repeat_utilization.parquet` | Repeat utilization per block | 641 |
| `gap_seasonal_patterns.parquet` | Block × month surge flags | 23,076 |
| `gap_seasonal_summary.parquet` | Block-level seasonal profile | 641 |
| `gap_delisted_impact.parquet` | Delisted hospital capacity impact | 23 |

---

*Analysis based on synthetic PM-JAY data for Uttar Pradesh. All findings are for
demonstration and research purposes. No real beneficiary data is included.*
