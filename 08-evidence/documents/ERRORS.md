Bug regarding the way the graphs looked Different on laptop and mobile - 

Backend and frontend dev servers are up locally and the full test suite is running in the background — I'll report results once it completes.

One thing to flag: I tried to get a fully logged-in browser session to screenshot-verify the fix myself (I have Playwright/Chromium available), but every attempt to touch auth_identities/sessions data — even read-only, even just to find a legitimate login identifier — was blocked by Claude Code's auto-mode classifier as auth-bypass-shaped. I'm respecting that and not working around it. So I haven't visually confirmed the fix myself; if you want that, you'd need to log in yourself and check, or loosen that Bash permission rule if you're comfortable with it.

That said, the fix itself is correct by construction, not just by inspection:

- .sparklineWrapper has a fixed CSS height of exactly 96px (FundSignal.module.css:125).
- The SVG's viewBox height is now CHART_HEIGHT = 96 — an exact match.
- The viewBox width is now chartWidth, measured live via ResizeObserver from the wrapper's actual rendered pixel width — not a hardcoded constant.
- preserveAspectRatio="none" was removed entirely.

Since viewBox dimensions now equal the rendered box dimensions exactly, the SVG-to-screen scale factor is exactly 1.0 on both axes, for any container width — so the r="4" active-point circle renders as a true circle and the line/curve geometry isn't stretched, regardless of whether the modal is 320px or 640px wide. That's why mobile never had this bug (its viewBox already happened to roughly match its render aspect) and why a hardcoded constant would've been the wrong fix (it only works for one width).