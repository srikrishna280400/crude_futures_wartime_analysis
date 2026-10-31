### 1. Product Outcome:

"Turn 7 months of market chaos into a 5-minute morning brief that lets one trader decide with evidence instead of narrative — where every piece of advice carries its own track record, and the product is trusted because it admits what it doesn't know, while also learning from its mistakes and every descision/prediction made."

Broken into the anatomy a PM would actually write:

- User: a solo self-directed trader (the user themselves — a real user with real money at stake, not a persona)
- From-state → to-state: from "every morning re-deriving context from news headlines, gut feel, and scattered charts — decisions with zero statistical memory" → to "one page: today's situation matched against history, with an honest confidence label on every call"
- Why this is the right outcome (the strategic call): P&L can't be promised — markets are partly manipulated. So the outcome is defined on the controllable layer: decision quality infrastructure. The bet: consistently better-informed decisions compound into better
  P&L; the product doesn't need to own the P&L to own the value.
- Measurable conditions of success:
  a. Every daily decision is backed by a matched historical situation with a stated hit-rate — not a vibe
  b. The advice stream has a public, growing track record (every past call scored against what actually happened)
  c. Trust metric: the system's "I don't know" days are as visible as its confident days
  d. Time-to-decision: minutes, not hours of chart-staring
- The product line drawn (and defended): decision-support, never an oracle. Saying "price will hit X" is a broken promise by design; "in situations like today's, this happened 63% of the time" is a promise the product can keep — forever.


### 2. Constraints — Defining the Playing Field before Designing the Solution

Before deciding what to build, I enumerated what the product has to survive. Two classes of constraints — one external (the market's forces), one self-imposed (the rules I bound my own solution with):

## i. External constraints — the forces the advice must make sense of:

- The situation itself is repetitive but shapeshifting — the war didn't stay one crisis; it cycled through recognizably distinct states (full-scale war → ceasefire-with-deal → ceasefire-without-deal → naval blockade with escalation flashpoints…). So the market's
  "rulebook" changed repeatedly over 7 months. Constraint accepted as the founding design decision: every piece of advice must be conditioned on which state the situation is in — the same day-type means different things in a war phase vs a ceasefire phase. This was
  carved into 12 chronological war phases as the product's primary context axis.
- Market forces beyond fundamentals — psychology-driven price suppression, sudden violent dumps, short squeezes: the market lies sometimes, so advice can't assume the tape is honest
- Structural mechanics — rising premiums near contract expiry, backwardation/contango regimes: the instrument itself distorts price, independent of news
- Recurring external events — Wednesday inventory releases, the Brent–WTI spread, nations re-routing supply via bilateral deals, strikes on energy infrastructure: a repeating calendar + shock events the product must contextualize every call against
- Time-of-day structure — different market sessions (Asian/European/US) move price differently: "when" matters as much as "what"
- The meta-constraint: volatility wasn't random — it was the sum of all of the above. So the opportunity wasn't "predict the market," it was map which force is dominating today


## ii. Self-imposed constraints — the rules I bound my own solution with (quality-of-evidence guardrails):

- No claim without historical evidence — every call must be grounded in matched past situations (Bayesian-Dirichlet style inference)
- No false discoveries — with hundreds of possible patterns, some will look real by chance; an explicit filter (Benjamini–Hochberg-style FDR) to not fool myself
- No overconfidence from thin data — small samples get pulled toward the average (hierarchical shrinkage) instead of being trusted at face value
- No oversized bets — position sizing bounded by both mathematical optimality (Kelly) and volatility of the current regime
- No self-graded homework — every pattern validated on data it wasn't derived from (walk-forward testing), never graded on its own homework
- No one-size thresholds — "big move" is defined relative to the current regime, not a fixed number (a 1% day in a war week ≠ a 1% day in calm markets)


The framing constraint (from a starting point of complete ambiguity): nothing about "how to mine patterns from this market" was given. The first structural decision was to define what a pattern even is — classifying each day by its price-movement type (day flags), cross-referenced against the day's news character. That choice — "a pattern is a repeatable (price-shape × situation-state × time-of-day) combination" — became the definition every downstream method inherited. Defining your primitive before choosing your method is the constraint-level decision; the war-phase axis and the day-type axis are its two children.

So the constraint stack reads, in order of how they shaped the design:
- Situation-state axis (war phases) — advice is phase-conditional
- Price-shape axis (day flags) — patterns are defined on repeatable price-movement types
- Market forces (manipulation, squeezes, expiry premiums, inventory calendar, supply re-routing, spread)
- Time structure (session windows, sub-hourly regimes)
- Failure mode (deviation analysis — what happens when the pattern breaks)
- Evidence rules (the six self-imposed quality guardrails)



### 3. Solution mapping → features → user stories → shipping

## i. Solution mapping — the answer to "what would it take to deliver the outcome":
The outcome demanded that one page per morning be true — so the solution mapped into three ingredient classes, then into features:
- Raw material: market data, flowing in daily, in every useful resolution
- Processing: turning that data into "situations" that can be matched and scored
- Delivery: a daily brief a non-technical reader can act on

## ii. Features defined (each traceable to an outcome condition):

- Feature: Universal situation grammar — every day classified by movement-type (trending, whipsaw, gap-and-hold, range-bound…), so any day can be compared to any other day. Serves: "decisions backed by matched history."
- Feature: Time-of-day lens — the day split into market-session windows, so advice can say "in the US session, this day-type usually does X." Serves: precision of the advice, not just direction.
- Feature: Situation-state conditioning — all analysis keyed to which war-phase state the world is in. Serves: advice that respects the regime.
- Feature: Pattern memory — which movement sequences reliably precede/follow which others. Serves: "what happened next last time."
- Feature: Failure-mode maps — explicit tracking of when the normal pattern breaks and what takes over. Serves: honesty + resilience.
- Feature: Evidence gate — every pattern graded for sample size, overconfidence filtered out. Serves: the trust contract.
- Feature: Live classification — every morning, today is automatically matched to a situation-state and day-type. Serves: zero-effort for the user.
- Feature: The daily brief — the one page where it all lands, in plain English. Serves: 5-minute time-to-decision.

## iii. User stories — the actual PRD behind the pipeline (the "questions" list was, in effect, my acceptance criteria):

Every feature above was specced backwards from the questions the user must never have to ask twice — these read like user stories with acceptance criteria attached:

- As the trader, when I open the brief I want to know "what kind of day is today, historically?" — so my first scroll gives me the match, not a data dump.
- "Which session window drives today, in which direction, under this news state?" — so I know when to be present and when to stay flat.
- "When the usual pattern fails, what takes over?" — so a broken pattern isn't a surprise, it's a mapped branch.
- "If P happened this morning, what followed it last time?" — so sequences, not single candles, drive my read.
- "How far does price usually travel on a day like this?" — so my targets and stops are regime-sized, not round-numbered.
- "Which windows are safest to enter, and which are stop-hunt traps?" — so danger zones are pre-labeled.
- "Do manipulative moves have a signature?" — so hostile price action is a recognizable archetype, not a shock.
- Every claim in the brief must show its evidence grade — n, confidence label, and when it's too thin, the brief says "don't rely on this."


## iv. Shipping — the part where the analysis project becomes a product

Three shipping decisions made that real:

# a. One feature, one engine, one output — the component contract.
Every feature from the solution map was shipped as an independent, self-contained program: takes inputs in, performs exactly its one job, writes versioned outputs to disk, exits. No engine reaches into another's internals; they communicate only through their published outputs. This is a product decision, not a code preference — it means any feature can be re-tested in isolation when something looks wrong, swapped without collateral damage, or re-run after a fix without re-running the world. It's the same discipline as keeping features independently shippable behind stable interfaces.

# b. One orchestrator — the daily operating rhythm.
A single master run-file chains all engines in strict dependency order — data comes in fresh, gets validated, classified, matched, graded, and lands as the daily brief — in one command. The daily operation became: append today's date, run the command, read the brief. That's a product cadence, not a developer task: the user's morning routine is one step, and the product's reliability is the predictability of that step.

# c. Incremental by design — shipping for the long run, not the demo.
Recomputing everything from scratch every day doesn't scale as an operating model, so the run was built to detect what changed since last time and only reprocess that. Full rebuilds happen when needed (minutes); routine daily updates complete in seconds. The shipping principle: a product that runs daily must be engineered for day 100, not day 1 — the demo being fast is worthless if the routine decays into a 2-hour chore nobody keeps up.


### 4. Optimizations, Iterations & Metrics — the continuous-improvement layer (in product terms)

After the first version shipped, the work shifted from "build it" to "make it trustworthy and durable." Iteration and metric-definition happened together — every wave below was triggered by a question the current metrics couldn't answer:

## Wave 0 — "What would 'working' even mean?" → defining the metric system before optimizing anything
- The founding metric decision: a single "credibility score" was rejected as the wrong instrument. One number can't catch different failure modes — a product can be directionally right, confidently wrong, economically useless, or falsely humble, and one blended score
  hides all four.
- Instead, a panel of complementary metrics was defined, each answering one distinct product question:
  a. Was the direction right? — hit rate, measured fairly against a naive baseline (not just "above 50%," which any trending market fakes)
  b. Are the stated confidence levels honest? — when the product says "70% likely," did it happen ~70% of the time? (calibration)
  c. Is the edge real after real-world costs? — profits minus fees and slippage, with a stated range of uncertainty, not a single lucky number
  d. Does the system know which situation it's in? — classification accuracy measured on data it wasn't tuned on
  e. Is it appropriately humble? — how often it declines to answer when evidence is thin, and whether declining saved the user from bad calls
- Design rule applied throughout: every metric must be measured on data the product never learned from. Metrics on data the product studied are a self-review, not a grade.

## Wave 1 — "Is the advice actually good?" → discovering nothing was keeping score
- Interrogating my own claim exposed that the product was grading its own homework (patterns validated on the same data they came from) and that yesterday's recommendations were never checked against what actually happened — zero resolved checks, zero track record. A
  feedback fiction, not a feedback loop.
- Fix: installed the missing loop — every recommendation is now automatically scored against reality the next day, building a growing, public track record. This loop also became the data source for every metric in the panel: no track record, no trustworthy numbers.

## Wave 2 — "Can we trust the headline numbers?" → the metrics got worse, and that was the win
- Measured honestly for the first time, the success rate dropped (from the flattering self-graded figure to a materially lower but real one). Treated as the fix working: before, marketing metrics; after, reality metrics.
- The report now permanently shows both numbers side by side — the self-graded figure and the honestly-measured one — so the gap between "how good it claims" and "how good it is" stays visible forever instead of being quietly buried.
- Grading fairness was tightened too: the boundary between "data the product studied" and "data it's being judged on" was derived from the data's own behavior, so near-neighbor information can't leak across the line.

## Wave 3 — "What should the product do when it doesn't know?" → making refusal a measurabl
- A brand-new situation arrived with almost no history. Old behavior: silently borrow a wrong situation's advice and present it with fake confidence — even though the system's own published self-assessment said it was unreliable (the signal existed; nobody consumed
  it).
- Fix: a three-gate gatekeeping rule — too little evidence, too little confidence, or toroduct explicitly says "don't rely on me today" and logs why. Refusal became a designedbehavior — and a metric (#5 on the panel): abstention rate is tracked and cross-checked
  against the losses it prevented.
- Plus: per-pattern freshness tracking — when a specific pattern's live performance decays well below its historical claim, it's flagged and demoted automatically. Patterns have a shelf life; the product now notices expiry.

## Wave 4 — "How does it learn from its own mistakes?" → designing the learning loop
- Three existential doubts, each resolved with design rather than hope: news can't be fed live → news only needs to say which rulebook applies, not predict headlines; the market is manipulated anyway → the product deals in probabilities-with-context, not promises, so
  manipulation shows up as mapped behavior, not broken predictions; patterns keep breaking → regimes drift, so every pattern is a decaying belief updated with every new day, not a permanent law.
- The honest self-audit: "does it learn from deviations today?" — answer: only implicitling from Wave 1 is what turned that hope into a mechanism.

Where the metrics landed (the outcomes they ultimately reported): ~290 validated recomme with a 63% direction hit-rate and a real, positive per-trade edge after costs — with theconfidence interval on that edge published, not hidden. Downside behavior measured too (worst sustained loss ~11%), and the honest OOS figures stated next to their flattering in-sample cousins. Every number traceable to a resolved track record, not a claim.



### 5. Systems Thinking & Level-Shifting — the deepest product skill in the project

## i. Level-shift 1 — "Is my classification right?" → "What level should classification even happen at?"

The founding decision — carving 7 chaotic months into 12 war-phase states and conditioning all advice on them — was a system-level bet. Iterations made everything downstream smarter, but the honest diagnosis that finally landed: the flaw wasn't anywhere in the machinery — it was at the level of what the system was keying on. 

Two structural tells, readable from the product's own failures: 
a. consecutive days sharing a phase label behaved nothing alike (the label was too coarse to predict), and 
b. similar days landed in different phases because a calendar line said so (the label was discriminating on the wrong axis). 

The response was a re-founding at the level of behavior instead of narrative — and the deliberate choice of method for that re-founding was clustering. If the goal is "days that behave alike belong together," then the grouping must be discovered from the data, not decreed by a human calendar: each day was converted into a measurable behavior profile (how big its body was, where its wicks sat, how it moved relative to recent days, its volatility character), and a statistical clustering method was let loose to find the natural groupings — with the number of groups not guessed in advance but derived from the data itself by testing which count best explains the structure. The results: days months apart that genuinely look alike now sit in the same group (the grouping became non-continuous by design), consecutive dissimilar days stopped being forced together, and the grouping comes with a descriptive label of its actual character ("strong downtrend," "whipsaw-dominant") instead of a geopolitical name.

Three further judgment calls rounded out the approach, each with its reasoning:
- First pass came out too coarse (3 groups for 146 days — the data collapsed most days into one "normal" bucket). Rather than accept it, the profiles were enriched with the day-shape classifications, and the data re-declared its structure: 7 groups, a better
  granularity–accuracy balance chosen by the same data-driven selection, not by preference.
- The day-shape labels themselves were found contaminated — they had been assigned via war-phase date ranges, so the entire historical record was re-labeled from raw price data alone before clustering on it. Fix the dependency before building on it.
- The mapping between groups and day-shapes was deliberately kept many-to-many — when asked whether each group should map 1:1 to one day-shape, the instinct was tested and rejected: forcing 1:1 would manufacture misclassifications to satisfy a tidy rule. Real market
  days are blends; the data-driven mix (each group carrying a measurable composition of day-shapes) is the accurate representation, so group composition is reported, not constrained.
- And it shipped without destroying anything: the new classification was built as a parallel branch — the original pipeline kept intact as a museum artifact, both coexisting side by side — so the re-founding could be validated end-to-end before ever replacing what
  worked. Also engineered to be incremental: a saved model classifies each new day without re-clustering history, so the daily operating rhythm survives the re-founding.

The second-order outcome: every classification, prediction, and accuracy claim downstream now rests on objective ground truth instead of subjective news judgment.


## ii. Level-shift 2 — "My granularity is wrong" → "Do I relabel, or do I add a layer?"

A prediction-quality problem surfaced in how coarse the time-slices were — hours of price action collapsed into one window meant violent moves inside it were structurally invisible. The obvious fix (re-cutting the time windows) was caught before execution as a systems-level trap: time labels are baked into every historical record at ingest, so relabeling would split the product's own history into two incompatible eras — everything learned under old labels vs. everything decided under new ones, apples-to-oranges forever.

The resolution was an architectural judgment about where change should live: instead of mutating the shared foundation, add a resolution layer on top — finer sub-slices computed from data that already existed, run identically across all of history and all future dates, so no era-break ever forms. Existing metrics stay valid; the brief simply gains a sharper lens beneath the aggregate. The trade-off (smaller samples per sub-slice) was handled with the same evidence-hygiene rules as everything else, not ignored.
