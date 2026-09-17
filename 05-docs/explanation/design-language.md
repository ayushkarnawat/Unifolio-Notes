# The design language, and the reasoning behind it

The exact values are in [design tokens](../reference/design-tokens.md). This is why they
are what they are.

**Source note:** two versions of the Design Brief exist in the batch-1 material. v1.1 is
a strict superset of v1.0 and is treated as canonical here. The only substantive
differences are that v1.1 resolves the Signature Element into "Fund Signal," adds a
research-sources appendix, and closes the open question about further design references.
v1.0 is retained unaltered as a source.

## The principles

1. **Restraint over decoration.** The product's job is to show someone their money
   clearly. Nothing on screen should be there because it looks nice.
2. **Game-like pacing, never game-like mechanics.** Momentum, reveal, and a sense of
   progress are welcome. Badges, points, streaks, and scores-as-rewards are not. The
   distinction matters because this is a financial product — pacing makes it pleasant to
   use, mechanics make it untrustworthy.
3. **Numbers are the interface.** Typography and alignment carry most of the design load.
   Hence tabular figures being mandatory rather than preferred.
4. **Every semantic colour pairs with a non-colour signal.** An arrow, a label, or a
   position — colour is never the sole carrier of meaning. This is an accessibility
   baseline, not a nice-to-have.
5. **Brand and semantics stay separate.** The brand green is not the gain green. See
   below.

## Why there are two greens

`color-accent` (`#22C55E`) is the brand. `color-positive` (`#16A34A`) is a gain. They are
in the same hue family, deliberately, so the palette reads as one system — and they are
deliberately not the same value, so a green number in a table is never mistaken for a
clickable brand element, and a brand button is never misread as "this went up."

The same logic produces the other two semantic colours. An unclassified badge is grey
(`color-neutral-badge`), not red, because "we could not determine this" is not a loss.
Stale data is amber (`color-warning`), not red, because old data is a freshness problem,
not a bad outcome. In a product about money, miscolouring these is not a cosmetic error.

## The Fund Signal

The one signature element. The brief asked for something that "feels distinct in an
ownable way, not just a static name."

**What the research found:**

- Every one of the eleven direct and indirect competitors reviewed, and MProfit itself,
  displays holdings as a static row — name, numbers, done. Nothing in this market gives
  an individual fund a visual identity beyond a logo icon.
- Outside this market, two patterns are established and proven, just never combined here:
  stock-trading apps commonly pair each holding with a small sparkline of its recent
  trend, right in the row; and current fintech design-system practice explicitly
  recommends that an asset's detail density *adapt* — full analytics on a large view,
  collapsing to "a simplified trend line and a single status indicator" in a compact one.
- Unifolio's own logomark already carries a shape language nothing else in this market
  uses: the arc inside the "o" reads as a partial gauge or dial. No competitor reviewed
  uses radial or arc language anywhere.

**The concept:** every holding gets a small radial arc — reusing the *exact* geometry of
the logomark, not a generic progress ring — whose fill represents that fund's performance
over a selectable period, paired with a sparkline on expansion or a wider viewport.
Direction uses the semantic colour system, never the brand accent, keeping brand identity
and performance signal cleanly separated.

It is a synthesis, not a copy: the arc comes from Unifolio's own already-locked brand
mark, which nothing in the product currently extends into the UI; the
sparkline-on-expand comes from general fintech practice rather than any one competitor;
and the combination, applied to individual mutual-fund holdings, is not something any
reviewed competitor does. It also satisfies principle 2 — an arc filling in as data loads
is a reveal, not a badge.

**This is a direction, not a finished design.** Whether the arc reads clearly at
holdings-table row size, how it behaves in a list of 30+ funds, and dark-mode legibility
are all real prototyping work that has not been done.

## Voice

Plain, specific, and never falsely reassuring. An error message names what went wrong and
what to do about it — the Summary-vs-Detailed statement error being the canonical example
of a message worth writing specifically rather than generically.

## Accessibility baseline

WCAG AA contrast on all text, including secondary text against the background. Colour
never as sole meaning. `prefers-reduced-motion` respected — every motion token has a
no-motion path, since the pacing that makes the product pleasant must not be a barrier.

## Resolved, so it is not re-asked

No further mood boards, sketches, or design skeleton are coming beyond the brand identity
already shared. This is a confirmed decision, not a gap. Design direction is grounded in
competitor and industry research rather than in reference material that does not exist.

## Related

- [Design tokens](../reference/design-tokens.md)
- [Screen inventory and flows](../reference/screen-inventory-and-flows.md)
