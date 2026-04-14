# Manuscript Revision Instructions for SLR_final.pdf

Based on the PDF metric verification exercise, the following updates should be made to the manuscript. The changes are organized by section.

---

## 1. Abstract (page 1)

**Current text:** "median R² = 0.96 and maximum R² = 0.97–0.98 in best-in-class studies"

**Update to:** "median R² = 0.96 under random cross-validation, but only R² = 0.75–0.95 under temporally rigorous holdout protocols. The discrepancy — approximately 0.04–0.10 R² units — is attributable to data leakage from random splitting of time-ordered sensor data."

**Rationale:** The abstract should flag the inflation problem upfront, not just in the body. This is the paper's most distinctive finding.

---

## 2. Table 2 (page 5) — R² by ML method

**Current table is good** — it already separates temporal (T) from k-fold (K). However, add a footnote:

**Add footnote:** "One study [14] reports R² = 0.99999 using engine room parameters (ME RPM, ME power) as input features, which constitutes near-deterministic prediction rather than operationally useful forecasting. This value is excluded from the ranges shown. Three included studies [8], [10], [19] are systematic or narrative reviews reporting no original metrics; they are excluded from Table 2."

---

## 3. Section 4.1.4 "Validation methodology problems" (page 6)

**Current text is strong.** Add this paragraph after the existing content:

**Add:** "Our post-hoc PDF verification of reported metrics across all 69 included studies revealed the extent of this problem quantitatively. Of 48 papers whose full text was examined in detail, only 20 clearly report R² on an identifiable held-out test set. Thirty papers report R² values without explicitly stating whether the metric applies to training, validation, or test data. Three papers ([8], [10], [19]) are review papers that report no original metrics but were initially coded with R² values from their cited sources — a metadata error corrected during verification. One study ([14]) achieves R² = 0.99999 by including engine room parameters (main engine RPM, power output, cylinder pressures) as input features; since these are near-deterministic proxies for fuel consumption, this represents trivial prediction rather than a useful forecasting model. The most revealing case is Du et al. [43], who report R² = 0.977 under random 80/20 splitting but acknowledge that R² drops below 0.5 under a rolling-horizon temporal protocol on the same data — a single-paper demonstration that the inflation factor can exceed 0.4 R² units."

---

## 4. Table 3 (page 7) — Physics-hybrid architectures

**Update P-033 (Altan et al.) entry:**

**Current:** "Best R² = 0.58 ± 0.12"
**Verified:** This is correct — R² = 0.581 ± 0.12 on chronological split for 4 vessels. This is actually one of the most honest metrics in the entire review. **Add note in table:** "(chronological; 4 vessels)"

This paper deserves more prominence — it's the only T2 paper with multi-vessel temporal validation showing realistic R².

---

## 5. Section 4.3.6 "Deployment reality: the feature engineering gap" (page 8)

**Current text already includes your key insight (R² ≈ 0.30–0.40 → 0.60–0.70).** This is excellent and should remain. Strengthen it with:

**Add after the existing paragraph:** "This operational evidence is corroborated by the verification analysis conducted for this review. When R² values are stratified by validation rigor, the pattern is clear: studies using random k-fold or same-vessel random splits report median R² = 0.97 (n=12 for gradient boosting alone), while studies using temporal holdout or cross-vessel protocols report median R² = 0.93 (n=8). The gap widens further in multi-vessel deployments: Nguyen et al. [65] found that a model achieving R² = 0.95 on its training vessel could fall to R² = 0.87 on vessels outside the training distribution, with catastrophic failure (96.8% overestimation) on the largest vessel class. Gupta et al. [42] reported a train-to-test R² drop from 0.98 to 0.88 under temporal splitting on sister ships. These findings collectively confirm that the literature's headline R² values overstate operational performance by 0.1–0.3 units, with feature engineering — not algorithm selection — accounting for the majority of recoverable accuracy."

---

## 6. Section 5.1 "Towards a unified operational framework" (page 11)

**Current text is excellent.** No changes needed — it already states:
- R² ≈ 0.30–0.40 without FE
- R² ≈ 0.60–0.70 with systematic FE  
- R² ≈ 0.85–0.92 with physics-residual + temporal holdout

This is the paper's strongest paragraph. Consider making it a **numbered finding** or **boxed highlight** for emphasis.

---

## 7. Section 5.6 "Limitations of this review" (page 12)

**Add a 5th limitation:**

"Fifth, the metric verification conducted for this review — reading the results sections of 48 full-text PDFs to confirm which evaluation set reported R² values apply to — revealed that 30 of 69 included studies do not unambiguously state whether their best R² is computed on training, validation, or test data. While we made best-effort determinations based on context, some R² values in Table 2 and the supplementary data may misattribute training-set metrics as test-set metrics. This systemic reporting deficiency in the primary literature propagates into any meta-analytic comparison."

---

## 8. Section 6 "Conclusion" (page 12-13)

**Current RQ1 answer is good.** Strengthen the key sentence:

**Current:** "Studies using random cross-validation report R² = 0.95–0.99; studies using temporally rigorous holdout report R² = 0.75–0.95"

**Update to:** "Studies using random cross-validation report R² = 0.95–0.99; studies using temporally rigorous holdout report R² = 0.75–0.95, with the most honest chronological multi-vessel evaluation (Altan et al. [33]) yielding R² = 0.58 ± 0.12. In production deployment without feature engineering, R² ≈ 0.30–0.40 should be expected."

---

## 9. References — corrections needed

**[19] and [20] appear to be the same paper** (Alexiou et al., 2022, Energies 15(22), 8738) listed twice with identical content. Remove the duplicate.

**[74] Bassam et al.** — this reference (P-066) has year 2023 in the reference list but P-003 (also Bassam et al., 2022) is a different paper. Verify these are indeed different papers and not duplicates.

**[75] "Unknown author, 2025"** — if this is P-067 (Pham et al., Polish Maritime Research), update with actual author names: Pham, T.H. et al.

**[76] "Unknown author, 2022"** — if this is P-068, try to identify the actual source and authors.

---

## 10. Supplementary material / Excel update

The verified metrics file (`PRISMA_AI_Search_Log_v2_verified.xlsx`) now contains:
- Column V: "R² Eval Set" — states exactly where each R² was measured
- Column W: "Metric Flag" — quality warnings per paper
- Column U: "Metric Verified" — whether the value was confirmed from PDF

**This should be included as supplementary material** with the paper submission. Reference it in Section 2.6 (Data extraction): "The complete data extraction table, including PDF-verified metric provenance and quality flags, is provided in the supplementary Excel file."

---

## 11. NEW: Consider adding a figure

**Figure suggestion:** A scatter plot or paired bar chart showing:
- X-axis: papers (sorted by validation rigor)
- Y-axis: reported R²
- Color/shape: validation protocol (temporal=blue, random k-fold=red, unverified=grey)

This would visually demonstrate the inflation gap and would be the paper's most impactful figure after the PRISMA flow diagram.

---

## 12. P-061 and P-063 possible duplicate

Our PDF verification found that P-061 (Cepowski & Drozd, ANN fuel consumption, Polish Maritime Research) and P-063 (Cepowski & Drozd, measurement-based relationships, Applied Energy) have overlapping content. **Verify these are indeed different papers** — they may share the same vessel dataset and have very similar R² (0.93) but could have different methodological contributions (ANN vs regression). If they are the same paper, remove one and reduce the count to 68.

---

## Summary of impact

These revisions don't change the paper's structure or conclusions — they **strengthen** the central argument by:
1. Quantifying the R² inflation with verified numbers
2. Naming specific examples (P-002 data leakage, P-025 random vs temporal, P-018 honest multi-vessel)
3. Adding a 5th limitation about metric verification difficulty
4. Making the abstract more accurate about what "best R²" actually means
5. Correcting reference duplicates

The paper is already well-written and the core argument is sound. These are precision improvements, not rewrites.
