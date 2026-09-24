# ADR-036 — Soccer model evaluation and market benchmarking

**Status:** Accepted design direction; Phase 4+ implementation deferred  
**Date:** 2026-09-24

## Context

The owner requested an evidence-oriented refinement, not a model implementation.
[ADR-008](ADR-008-soccer-baseline-model.md) preserves the statistical-first baseline.
The existing Prediction, ModelVersion and BacktestRun concepts can carry forecast
and evaluation evidence without a duplicate ForecastSnapshot entity.

Later data decisions take precedence over broad early research aspirations:
[ADR-026](ADR-026-replay-dataset-manifest.md),
[ADR-029](ADR-029-football-data-season-replay.md),
[ADR-034](ADR-034-synthetic-market-quotes.md) and
[ADR-035](ADR-035-odds-api-soccer-adapter.md) do not grant historical eligibility.
Current retained results/quotes are replay-only or synthetic-only, not model-ready
point-in-time inputs. A new research dataset contract/evidence review is required.

## Decision

### Benchmarks and promotion

Evaluate soccer models chronologically on frozen, eligible datasets against both
documented simpler statistical baselines and a reproducible no-vig market
consensus. Do not claim model improvement without robust forward/OOS improvement
against both on the declared task, horizon, common evaluation cohort and metrics.
The market is a strong benchmark, not assumed correct or unbeatable. Report mixed
results rather than selecting whichever metric, league or horizon looks best.
Candidate/shadow status and valid negative findings do not require beating it.

Predeclare rolling/expanding training, validation and untouched test windows,
retraining cadence, calibration procedure, comparison metrics and promotion rule.
Fit preprocessing, recency, feature selection, calibration, hyperparameters and
ensemble weights only on earlier training/validation data. Account for repeated
model/strategy searches; never tune on the final test set. Persist failed trials
and exclusions as well as successful ones. Later labels are evaluation targets,
not decision inputs; historical training labels must be available by the fit cutoff.

### Reproducible market consensus

Create a derived MarketConsensusSnapshot, distinct from a single venue's
MarketSnapshot or an executable Quote. Pin complete mutually exclusive outcome
sets for the same canonical market, period, line and settlement rules. Retain
source and venue identities separately and deduplicate repeated observations of
the same venue obtained from multiple sources.

Version the eligible venue universe, source precedence, freshness limits,
as-of selection, missing/stale/excluded quote reasons, minimum coverage,
aggregation order and weighting. De-vig complete per-venue sets before aggregation
under an explicit policy; alternative constructions are versioned challengers.
Do not synthesize a bookmaker by selecting the best price for each outcome, or
present an aggregate probability as a tradeable quote. Coverage below the declared
minimum means benchmark unavailable, not silent fallback. Report coverage and
matched-cohort counts; do not impute missing historical prices from later ones.

De-vig is pluggable: MULTIPLICATIVE, SHIN and POWER are candidate methods, with
method/version, parameters, numeric tolerance and failure policy retained. No
method is universally preferred. Compare sensitivity to method, venue selection
and dispersion; this uncertainty is distinct from model uncertainty. Phase 4
needs this narrow deterministic research baseline before Phase 5's opportunity
engine, which reuses it rather than duplicating de-vig logic.

### Horizon and point-in-time rules

Use a versioned ForecastHorizon policy (illustrative labels: OPEN, T_MINUS_24H,
T_MINUS_6H, T_MINUS_60M, LATEST_PREMATCH). Define OPEN by the first eligible observed
market under the declared coverage policy, not an unknowable universal opening.
Define LATEST_PREMATCH with a cutoff/freshness rule, not the latest stored record.
Pin actual decision time, scheduled kickoff as known then, selection tolerance,
rescheduling/missing-horizon policy and realized lead time. Compare predictions
and consensus at the same horizon; never backfill earlier horizons with lineups,
injuries, odds, xG revisions or closing prices that arrived later.

Conceptually, features.as_of(decision_time) and quotes.as_of(decision_time) must
include only facts and context dependencies whose evidenced available_at is no
later than that time. Effective/observed/ingested clocks, mapping cutoff and
snapshot creation are not substitutes. Unknown availability fails eligibility.
Retain model training cutoff and artifact readiness as well as prediction
generation time; a historical replay generated today must be labelled simulated,
not masquerade as a forecast published then. Frozen replay does not prove no leakage.

### Evaluation and uncertainty

Prioritize log loss, Brier score and calibration/reliability, with paired deltas
against the market and simpler baselines. Specify outcome space, multiclass Brier
convention, probability clipping policy (if any), calibration bins and sample
counts so reports are comparable. Compare 1X2 benchmarks on 1X2 probabilities;
do not compare score-distribution likelihood directly with a 1X2 market score.

Separately report estimated EV, CLV, realized ROI/P&L, drawdown, volatility and
sample count under explicit costs, fills and settlement assumptions. Classification
accuracy and win rate are secondary diagnostics, not primary optimization targets.
Segment by league, season, forecast horizon, market type, odds bucket and selection
type (e.g. home/draw/away). Add confidence intervals/bootstrap as the framework
matures, respecting event/time dependence rather than treating correlated bets
as independent samples. Small segments and missing coverage must remain visible.

ModelUncertainty is versioned evidence, not the win probability itself or an
unexplained confidence score. Support calibration uncertainty, sample support,
competition coverage, freshness, parameter uncertainty, stability, disagreement
and horizon effects. Record estimator/method, scope, inputs, limitations and
unavailable components; no universal estimator or interval meaning is selected.

Positive CLV can be evidence of earlier information discovery but is not proof of
sustainable profitability. Pin entry/closing quote selection, market semantics,
closing cutoff and de-vig convention. Closing data may be a later diagnostic, never
an earlier forecast feature. Continue measuring outcomes, calibration, uncertainty,
sample size and robustness; predictive lift alone is not an execution/profit claim.

### Decision boundaries

Keep model probability, raw estimated EV, uncertainty/reliability and actionable
strategy qualification separate. Pricing computes EV from probabilities and
offered executable prices with fees/slippage/settlement assumptions where relevant.
Model and market/de-vig uncertainty inform the versioned strategy's qualification
or abstention; they are not an arbitrary extra term in the EV equation. No universal
confidence-adjusted edge formula or fixed threshold is selected. Market disagreement
alone is insufficient. Risk approval remains a subsequent independent gate.

Market-aware challengers must identify market inputs, consensus/de-vig dependencies
and timestamps in ModelVersion and Prediction lineage. Their comparison with the
market measures incremental information, not independent fundamentals skill.
An ensemble containing market-derived inputs is also market-aware. Models never
output BET/NO_BET; strategy and pricing own actionability.

Fractional Kelly is a sizing research benchmark only, not a production default;
full Kelly is not the default. Eventual sizing must obey maximum position, event,
participant and correlated exposure, bankroll-at-risk, daily/weekly loss controls
and model-quality/confidence constraints. No real-money or implemented risk change
is authorized. Unsupported dependence cannot be waved away by a sizing formula.

## Consequences, limitations and deferred choices

- Phase 4 can finish with reproducible negative findings and no promoted challenger.
  Every promotion needs documented incremental evidence; no family is promised to win.
- Goals/results-only baselines are allowed on eligible data; xG remains high
  priority but is not a paid-data prerequisite for the first baseline.
- Consensus construction, horizon tolerances, uncertainty estimators, promotion
  thresholds and ML libraries require subsequent empirical specifications. No new
  dependency, deployable, schema migration, public API or provider permission is added.
- These are design requirements, not retrospective additions to strict receipt
  codecs. Phase 3 ingestion and all existing availability/rights restrictions remain.
- [Parlay Lab](../product/feature-specs/parlay-lab.md) requires validated joint-model
  coverage; marginal forecast success alone cannot support correlated parlay pricing.

## Research provenance and limits

The owner's supplied research synthesis motivates these requirements; no new
EdgeEagle performance study or exhaustive latest-literature review is claimed.
Primary references checked on 2026-09-24 provide methodological grounding:

- Gneiting and Raftery (2007), [Strictly Proper Scoring Rules, Prediction, and
  Estimation](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf),
  supports probability-oriented scoring rather than classification-only evaluation.
- Clarke, Kovalchik and Ingram (2017), [Adjusting Bookmaker's Odds to Allow for
  Overround](https://www.sciencepg.com/article/10.11648/10026106), compares de-vig
  approaches on specific datasets. Its findings are not a universal ranking for
  current soccer markets or evidence of exploitable profit.

The benchmark/promotion policy is EdgeEagle's design decision, not a theorem from
these papers. No claim is made that Dixon-Coles beats bookmakers, xG ensures
profit, ML dominates statistics, favorite-longshot bias remains exploitable,
any market is inherently inefficient, or parlays are inherently positive EV.
