# The Unifolio Fund Score — What It Is and How It Works

*A plain-language explanation for anyone at Unifolio talking to users, partners, or
press about how we score mutual funds. No engineering detail — just what the score
means and why we built it this way.*

## 1. What the score answers

Every mutual fund has a story told through dozens of numbers — returns, volatility,
expense ratios, category rankings. Most people don't have the time or background to
weigh all of that themselves. The Unifolio score answers one simple question as
honestly as we can: **"How good is this fund, really — compared to its true peers?"**

We boil that down to a single number and a 1-to-5 tier, but — unlike some of the
score badges you might have seen elsewhere — we never hide the reasoning behind it.
Every score comes with its full breakdown, so a user can always see *why* a fund
scored the way it did, not just the final number.

## 2. The three ingredients

Think of the score as a report card with three subjects, each graded against every
other fund in the same category (so a large-cap equity fund is only ever compared
to other large-cap equity funds, never to a debt fund or a small-cap fund):

- **Return (45% of the grade).** How well has the fund actually grown investors'
  money over the medium-to-long term, compared to its category peers? This is the
  biggest single ingredient, because returns are still the main reason people invest.
- **Risk (30% of the grade).** How much did the fund actually *lose* on its bad
  months, compared to peers? We deliberately only look at *downside* — the bad
  months — not overall up-and-down bounciness. A fund that swings up a lot isn't
  "risky" in the way that matters to an investor; a fund that loses money hard in
  bad months is. Lower downside risk grades higher here.
- **Consistency (25% of the grade).** Does the fund reliably beat the "typical"
  fund in its category, month after month, or does it have a few lucky great years
  propping up an otherwise unremarkable track record? We look back over rolling
  12-month windows and check how often the fund beat its category's middle-of-the-road
  performance. A fund that wins consistently scores higher here than one that wins big
  occasionally and loses the rest of the time.

These three subject grades are combined using the weights above into one blended
number, and that blended number is then ranked one more time against every peer
fund's blended number — so the final score always reflects genuine standing within
the fund's own category, not an absolute number that means different things in
different categories.

## 3. Why it's different from Morningstar, CRISIL, and apps like PowerUp

Most fund-rating products on the market today are built on the same handful of
ideas — Morningstar and CRISIL-style star ratings, or a simple Good/Average/Poor
bucket the way some newer apps present it. We didn't want to just repackage one of
those. The Unifolio score borrows the best-established idea from that world (grading
funds against true category peers) but adds two ingredients most of those products
don't isolate on their own:

- **Downside-only risk**, instead of a generic volatility number that penalizes a
  fund equally for swinging up and swinging down.
- **Consistency as its own graded ingredient**, instead of folding it invisibly into
  a return number or leaving it out entirely. A fund that wins slowly and steadily
  and a fund that wins in one spectacular year look identical on a plain returns
  chart — they should not look identical on a fund quality score.

Together, these are the two concrete ways the Unifolio score is a genuinely
different formula from what's already in the market, not a relabeled version of it.

## 4. The cost adjustment

Once the Return/Risk/Consistency grade is calculated, we apply one small, final
adjustment based on cost: a fund that's noticeably *cheaper* than its category peers
(lower expense ratio) gets a small bonus, and a fund that's noticeably *pricier*
gets a small penalty. This nudge is intentionally small — cost matters, but it
shouldn't be able to override a fund's actual investment quality. If a fund's cost
is close enough to the category average, no adjustment is applied at all; the nudge
only kicks in once the difference is meaningful.

## 5. How to read a score — a worked example

Say a large-cap equity fund is being scored against its full category of peers:

1. **Return grade:** the fund's medium/long-term growth ranks better than 78% of
   its peers → a Return percentile of 78.
2. **Risk grade:** the fund's downside losses in bad months rank better (i.e.
   smaller losses) than 65% of its peers → a Risk percentile of 65.
3. **Consistency grade:** the fund beat its category's typical performance in
   rolling 12-month windows 70% of the time → a Consistency score of 70.
4. **Blend:** `(45% × 78) + (30% × 65) + (25% × 70) = 72.1`
5. **Re-rank:** that blended 72.1 is then compared against every peer fund's own
   blended number, and lands at the 76th percentile overall.
6. **Tier:** a percentile of 76 falls in the "top 40%" band → **Tier 4 of 5**.
7. **Cost adjustment:** this fund happens to be meaningfully cheaper than its
   category average, earning a **+0.25 bonus**.
8. **Final score:** `76 + 0.25 = 76.25`.

That final number, its tier, and each of the three underlying ingredient
percentiles are all shown together — never just the bare "76.25" on its own.

## 6. What it deliberately is not

The Unifolio score is a modeling opinion built on historical data — it is **not** a
guarantee of future performance, and it is **not** a neutral, universally-agreed-upon
fact about a fund. Two reasonable methodologies can and do disagree on how to score
the same fund; ours is one considered point of view, built and documented
transparently, not the only possible answer. We never present it to users as
anything more than that.

## 7. Where it lives in the product

Users see the Unifolio score in two places:

- **On a fund's own detail view**, showing that individual fund's full score
  breakdown — tier, final score, and each of the three ingredient grades.
- **On the portfolio-level view**, showing one rolled-up score for a user's entire
  portfolio (or a single family member's holdings), weighted by how much money is
  actually invested in each fund — so a small, highly-scored fund doesn't drown out
  the score of a fund the user is much more heavily invested in.
