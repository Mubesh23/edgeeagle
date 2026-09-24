# Parlay Lab Feature Specification

**Product:** EdgeEagle  
**Status:** Draft  
**Owner:** Product / Quant Research  
**Parent PRD:** [`../PRD.md`](../PRD.md)  
**Architecture:** [`../../architecture/TDD.md`](../../architecture/TDD.md)

## 1. Purpose

Parlay Lab is EdgeEagle's quantitative workspace for constructing, pricing, comparing, and explaining multi-leg sports-market positions.

The feature must answer a pricing question, not a prediction question:

> Does the offered parlay price adequately compensate for the joint probability, correlation, uncertainty, and risk of the included legs?

Parlay Lab must not reduce analysis to payout size, win probability alone, or an opaque "good/bad" score.

## 2. Product Principles

Parlay Lab follows the platform-wide **Price, Not Picks** principle.

The feature must:

- compare offered price with EdgeEagle fair price;
- model the joint probability of all legs;
- make correlation treatment explicit;
- show expected value and uncertainty;
- explain how each leg changes the overall position;
- distinguish model-derived analysis from market-derived information;
- avoid guarantees, "locks," or certainty language;
- use deterministic backend calculations for probability, pricing, EV, risk, and correlation-sensitive logic.

The LLM/agent may explain a structured evaluation but must not independently calculate or override authoritative parlay analytics.

## 3. Scope

### 3.1 Core capabilities

Users should be able to:

- add and remove selections;
- view the offered combined price;
- view break-even probability;
- view EdgeEagle fair joint probability;
- view EdgeEagle fair odds;
- view estimated expected value;
- inspect correlation between legs where supported;
- inspect model-confidence and data-quality warnings;
- compare the parlay with equivalent straight positions;
- see how each leg changes parlay EV, probability, and risk;
- compare counterfactual versions of the parlay with one or more legs removed;
- save a parlay;
- paper trade a supported parlay;
- ask the agent to explain the evaluation.

### 3.2 Deferred capabilities

The following may be delivered after the initial Parlay Lab release:

- exhaustive optimization across large candidate sets;
- automated best-subset search across many legs;
- real-money parlay execution;
- full same-game correlation support for every market/sport;
- live/in-play parlay repricing;
- user-defined correlation models;
- advanced portfolio optimization across parlays and straight positions.

## 4. Evaluation Output

Every supported parlay evaluation should return, where available:

- offered parlay odds;
- market-implied / break-even probability;
- fair joint probability;
- fair odds;
- expected value;
- estimated variance or other supported risk measure;
- correlation treatment/method;
- model confidence;
- data freshness;
- warnings and unsupported-assumption flags;
- comparison with equivalent straight positions.

The UI must clearly distinguish **offered price**, **fair price**, **probability**, **EV**, and **confidence**.

## 5. Correlation Rules

### 5.1 Independence is an assumption, not a default

Cross-event legs may use probability multiplication only when independence is reasonably justified by the supported pricing model.

The system must never silently assume that same-event or otherwise materially related legs are independent.

### 5.2 Correlated legs

Where legs are correlated, the fair joint probability must use one of:

- a sport-specific joint outcome distribution;
- Monte Carlo simulation from a validated generative model;
- another validated correlation/joint-probability method.

The evaluation must expose which method was used.

For score-derived soccer same-game combinations, prefer exact enumeration over the
modeled joint home/away score matrix when every leg's settlement predicate can be
represented by it. Sum the probability of score cells satisfying all legs; do not
multiply marginal probabilities. Exact computation is conditional on the model,
not certainty about the real outcome. Record matrix support, tail/truncation
treatment, period/settlement semantics and model/pricing versions. A finite matrix
must not silently discard residual probability mass. Player props, cards and
half-time/full-time combinations are not covered merely by a full-time score matrix.

### 5.3 Joint-model coverage

Keep computational coverage separate from confidence. Conceptual categories:

| Coverage               | Meaning                                                                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `EXACT`                | All legs representable by a validated joint distribution and evaluated by enumeration/analytic calculation; model uncertainty remains.                  |
| `SIMULATED`            | Validated generative joint model covers all legs; retain algorithm/version, sample count, seed and Monte Carlo error separately from model uncertainty. |
| `INDEPENDENCE_ASSUMED` | Multiplication only with documented justification for independence and explicit limitations; never a fallback for correlated legs.                      |
| `UNSUPPORTED`          | Missing validated joint coverage or settlement semantics; authoritative joint probability, fair odds, EV and dependent risk are unavailable.            |

These are future conceptual values, not a generated API enum. Retain coverage for
the whole evaluation and its dependency groups; exact within-event coverage does
not make a cross-event independence assumption exact. Mixed evaluations expose
each component and must not hide weaker assumptions behind an EXACT label.
Standalone leg values can remain available when the joint evaluation is unsupported.

### 5.4 Unsupported correlation

If EdgeEagle cannot model a material dependency reliably, it must return a warning or unsupported status rather than fabricate precision.

Examples:

- `CORRELATION_UNKNOWN`
- `JOINT_MODEL_UNAVAILABLE`
- `LOW_SAMPLE_SUPPORT`

The UI must distinguish a supported but uncertain estimate from unavailable joint
pricing. If a material dependency has no validated joint model, return UNSUPPORTED
with reasons and no fabricated joint probability/EV or numerical correlation
adjustment. Low-support estimates from a validated model may carry uncertainty
warnings according to a versioned policy. The LLM/agent must never fill missing
joint coverage numerically or turn an unsupported result into a recommendation.

## 6. Leg-Level Attribution

For each leg, EdgeEagle should calculate or expose, where supported:

- standalone model probability;
- standalone fair odds;
- standalone offered odds;
- standalone expected value;
- joint probability before adding the leg;
- joint probability after adding the leg;
- parlay EV before adding the leg;
- parlay EV after adding the leg;
- incremental EV contribution;
- incremental risk/variance contribution;
- correlation contribution or correlation relationship with existing legs;
- model-confidence contribution or warnings.

This enables explanations such as:

> Adding this leg increases the offered payout, but reduces estimated parlay EV.

or:

> This leg has negative standalone EV and weakens the overall combination.

The product should not imply that a positive incremental contribution guarantees a favorable outcome.

## 7. Counterfactual Analysis

Parlay Lab should support deterministic counterfactual evaluation.

At minimum, for an `N`-leg parlay, the system should be able to compare the current parlay against versions with each single leg removed.

For each counterfactual, show changes to:

- offered odds where a venue quote is available;
- fair joint probability;
- fair odds;
- expected value;
- risk/variance;
- correlation profile.

Example product explanation:

> Removing Leg 4 reduces payout but increases estimated EV because Leg 4 is priced worse than the rest of the combination.

Counterfactuals should be labeled as model-based comparisons, not recommendations or guarantees.

Re-evaluate joint-model coverage for every counterfactual. Missing offered parlay
or reduced-parlay prices must not be invented by multiplying straight prices;
price-dependent EV comparisons remain unavailable or explicitly hypothetical.

## 8. Straight-Bet Comparison

When equivalent straight prices are available, Parlay Lab should compare the parlay with taking the legs separately.

The comparison may include:

- aggregate stake assumptions;
- expected value;
- payout distribution;
- variance;
- correlation/exposure;
- bankroll impact;
- price differences created by the parlay quote.

The comparison must make stake assumptions explicit.

## 9. Price Sensitivity

Parlay Lab should support price-sensitivity analysis.

Where mathematically defined, show:

- current offered price;
- fair price;
- break-even price;
- price corresponding to configurable EV thresholds;
- how EV changes as the offered price changes.

Example:

> Current price: +450  
> Fair price: +390  
> Minimum price for +5% estimated EV: +411

Price sensitivity reinforces the principle that the same selections may be attractive at one price and unattractive at another.

## 10. Structured Feedback

The backend may provide deterministic classifications that the UI and agent translate into plain language.

Example value classifications:

- `POSITIVE_EV`
- `NEAR_FAIR_VALUE`
- `NEGATIVE_EV`

Example correlation classifications:

- `LOW_CORRELATION`
- `MATERIAL_CORRELATION`
- `HIGH_CORRELATION`
- `CORRELATION_UNKNOWN`

Example confidence classifications:

- `HIGH_MODEL_CONFIDENCE`
- `MODERATE_MODEL_CONFIDENCE`
- `LOW_MODEL_CONFIDENCE`

Thresholds must be configurable, versioned where they affect research reproducibility, and not presented as universal truths.

The product should avoid a single opaque numeric "parlay score" unless its construction is transparent, validated, and demonstrably useful.

## 11. Agent Experience

The agent may answer questions such as:

- "What do you think about this parlay?"
- "Which leg hurts this parlay the most?"
- "What happens if I remove Leg 3?"
- "Is the payout compensating me for the correlation?"
- "Would these be better as straight positions?"
- "At what price does this become positive EV according to our model?"

The agent must obtain numerical claims from the authoritative parlay evaluation capability.

Conceptually:

```text
User
  ↓
EdgeEagle Agent
  ↓
evaluate_parlay(...)
  ↓
Parlay Pricing / Evaluation Engine
  ↓
Sport probability distribution + correlation model + market prices
  ↓
Structured ParlayEvaluation
  ↓
Agent explanation
```

## 12. Paper Trading and Portfolio Integration

A saved/evaluated parlay may become a paper position when the required price, model, and market metadata are available.

A paper parlay position should retain:

- selections and canonical market IDs;
- venue/data-source provenance;
- offered price at entry;
- fair joint probability at entry;
- fair odds at entry;
- EV at entry;
- correlation method/version;
- model versions;
- prediction timestamps;
- evaluation timestamp;
- stake;
- settlement state;
- realized P&L after settlement.

Portfolio risk should treat the parlay as a position while also retaining leg-level exposure for correlation/exposure analysis.

## 13. Desktop and Mobile UX

### Desktop

Desktop is the primary deep-analysis surface and should support:

- full parlay builder;
- leg table;
- joint pricing summary;
- correlation details;
- counterfactual comparisons;
- straight-vs-parlay comparison;
- price sensitivity;
- save and paper-trade actions;
- agent side-panel context.

### Mobile

Mobile should initially support:

- viewing/editing a manageable parlay;
- core fair price / EV / probability summary;
- warnings;
- leg-level impact summaries;
- saved parlay review;
- agent explanation;
- paper-trade action where supported.

Complex optimization/research views may remain desktop-first.

## 14. Domain/API Contract Expectations

The authoritative backend should expose a structured parlay-evaluation capability rather than embedding calculations in UI or agent code.

Conceptually:

```text
ParlayEvaluation
  selections[]
  offered_odds
  market_implied_probability
  fair_joint_probability
  fair_odds
  expected_value
  estimated_variance
  correlation_method
  joint_model_coverage
  dependency_group_coverage[]
  joint_model_version
  uncertainty_evidence
  forecast_horizon
  confidence
  warnings[]
  straight_bet_comparison?
  counterfactuals[]
  price_sensitivity?
```

Each leg evaluation should conceptually support:

```text
ParlayLegEvaluation
  selection_id
  standalone_probability
  standalone_fair_odds
  standalone_offered_odds?
  standalone_ev?
  joint_probability_before
  joint_probability_after
  parlay_ev_before
  parlay_ev_after
  incremental_ev
  incremental_variance?
  correlation_contribution?
  warnings[]
```

Exact schemas, field types, endpoint shape, and versioning belong in the API/domain design and TDD.

Unsupported joint evaluations make dependent numeric outputs unavailable with
reasons, not zero. Preserve horizon/decision time, prediction/pricing versions,
input provenance and simulation/tail policies for reproduction. Coverage does not
establish historical eligibility or turn raw EV into actionable strategy approval.

## 15. Research and Validation Requirements

Parlay pricing logic must be testable independently from UI/agent behavior.

Validation should include, as appropriate:

- known independent probability cases;
- deliberately correlated synthetic cases;
- Monte Carlo convergence tests;
- deterministic-seed reproducibility where simulation is used;
- comparison with analytically solvable joint distributions;
- regression tests against historical parlay/market data when licensed and available;
- calibration checks for joint probabilities;
- sensitivity tests for price and model inputs;
- explicit unsupported-correlation cases;
- exact score-cell enumeration against analytically known same-game examples;
- matrix tail/normalization and incompatible settlement/period rejection;
- mixed dependency-group coverage without overstating exactness;
- unsupported joint outputs staying unavailable in backend, UI and agent responses.

A correlation model should not be promoted to production merely because it improves historical ROI; probability calibration and leakage-safe validation matter.

## 16. Acceptance Criteria

The initial Parlay Lab capability is complete when:

1. A user can submit at least two supported selections for evaluation.
2. For supported combinations and supplied prices, EdgeEagle returns offered price, break-even probability, fair joint probability, fair odds, and EV; unavailable inputs/results remain explicit.
3. The system explicitly reports the correlation method/assumption, joint-model coverage and model uncertainty separately.
4. Same-event legs are never silently treated as independent.
5. Unsupported material correlation produces an UNSUPPORTED status with reasons, without invented joint probability, fair odds, EV or dependent risk.
6. The system can expose leg-level standalone value and incremental impact where supported.
7. Single-leg-removal counterfactuals can be generated deterministically.
8. Equivalent straight-position comparison is available when source prices exist.
9. Price-sensitivity information can be produced from fair probability and offered price.
10. The agent can explain the structured result without independently recalculating authoritative analytics.
11. Evaluations are reproducible from retained model/version/timestamp/provenance metadata.
12. Unit/fixture tests cover core independent, correlated, and unsupported cases.

## 17. Open Questions

- Which soccer market combinations will receive first-class same-game joint pricing in the first Parlay Lab release?
- Which correlation metrics are useful to expose directly to users versus only through warnings/explanations?
- What minimum confidence/sample thresholds should suppress or qualify an evaluation?
- How should venue-specific same-game parlay pricing be represented when the venue does not expose decomposed leg prices?
- When should best-subset optimization be introduced, and what guardrails prevent overfitting candidate combinations?
