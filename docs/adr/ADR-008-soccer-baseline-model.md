# ADR-008 — Interpretable Soccer Baseline

**Status:** Proposed  
**Date:** 2026-09-22  
**Refined:** 2026-09-24 (research design only; no model implemented)

## Context

Soccer V1 needs inspectable assumptions, reproducible fits and a distribution that
can price several markets consistently. A statistical-first baseline makes data,
calibration and leakage failures easier to investigate before adding complexity.
This preserves the original decision; it does not assert that a particular model
outperforms bookmakers or produces profitable strategies.

## Decision

Start with team strength, attack/defense and home advantage feeding an independent
Poisson, then Dixon-Coles-style joint score distribution. Market pricing and
strategy qualification remain outside the prediction model.

Use the following research/evaluation ladder, not a requirement to productionize
every family:

1. Reproducible no-vig market-consensus benchmark.
2. Elo / simple team-strength baseline with documented outcome-probability mapping.
3. Independent Poisson.
4. Dixon-Coles.
5. Dynamic and/or bivariate Poisson challenger.
6. xG-enhanced score model.
7. Bayesian / richer statistical challenger where justified.
8. Probability-producing ML challengers: logistic models where appropriate, then
   gradient boosting; no library is selected.
9. Explicitly identified market-aware challenger.
10. Calibrated ensemble only when repeatable chronological OOS evidence justifies it.

xG/xGA and related shot-quality information are high-priority features when rights,
coverage, point-in-time availability and operational cost permit. Goals/results
can establish the earliest baseline on an eligible dataset without xG. Neither
xG nor an imported results file automatically establishes profit or eligibility.
Retain provider definition/version and revision timing for advanced statistics.

Recency is empirical: compare rolling windows, exponential decay and dynamic
latent strength. Tune competition-aware windows/decay only inside chronological
training/validation folds; there is no universal decay rate.

Models output probabilities/distributions, never BET/NO_BET. A direct market
probability challenger does not automatically provide a coherent joint score
distribution or qualify for score-derived/parlay pricing. Market-aware families
must disclose odds inputs and dependencies, separately from independent
fundamentals models.

Follow [ADR-036](ADR-036-soccer-model-evaluation-and-market-benchmarking.md) for
same-horizon simple-statistical and market benchmarks, log loss/Brier/calibration,
uncertainty and promotion evidence. Complexity must earn robust forward/OOS
incremental value, not just improved in-sample fit, accuracy, win rate or ROI.

## Consequences

Model selection remains empirical. Candidate or shadow experiments may fail;
negative results are retained rather than forcing promotion. Statistical-first
does not prohibit ML research, but ML and ensembles follow strong baselines and
must justify added maintenance, data and computation costs. Model artifacts,
feature definitions, fit/calibration windows and evaluation policy are versioned.
No ML dependency, training code, paid data acquisition or production activation is
authorized by this refinement. The current Phase 3 adapter scope is unchanged.

## Related

- [TDD](../architecture/TDD.md)
- [PRD](../product/PRD.md)
- [Roadmap](../roadmap/implementation-roadmap.md)
