- [x] -analytics dashboard breakdown (how each element is implemented) -
- [x] -review analytics formulae
- [ ] -regular plan classification on import review screen
- [ ] -loading speeds - ALREADY Fixed - needs more refinement?
- [ ] -switching between dashboards - Fixed - needs more refinement ?
- [x] -active sips  - Okay. This is interesting. Can you also identify if there any other kinds of features like what we have identified as an active SIP? That might have a fully built backend and frontend but they're not showing up on the dashboard. Is there any feature like this that are still there?
- [x] -move distributor analysis to portfolio view
- [ ] -add pan (cas should be distinguished based on PAN) - resolving the pan persistence issue faced both my the MF varation we are bulding rn and also the stocks variation
- [x] -remove warnings from import review
- [ ] -broker analysis/amc level analysis (top funds by amc): there should be a clickable button at both fund and amc level that will open a full page description which will show fund managers, other funds by that manager, etc
- [x] another issue that I was able to identify was on the login, where, if, for example, I am not trying to sign up, I am trying to log in. When I'm trying to log in, if the number is already registered, already has data on it, and I'm currently on the screen where it is sending the OTP, I want the number to get OTP verified so I can go into my dashboard.For example, a number that I've currently stopped on is 9011097679, and it is still just sending OTP, sending OTP, sending OTP. It's not going to the verification screen, nor has it sent any. It's just not going to the verification screen, even if it's stopped for now. That's what happened, so I don't understand why this is happening here.
- [ ] Migration-Plan-SQLite-to-Postgres.md - is everything we have done till now being prepared according to this  - backend + Frontend
  [ ]"move to Redis/similar if/when this backend ever runs multiple workers" - I think it is time to start moving to Redis to make things faster - Confirmed the architecture: app/db/session.py uses create_engine — a fully synchronous SQLAlchemy engine, no async driver. And I noticed an existing comment in pdf_export.py ("move to Redis/similar if/when this backend ever runs multiple workers") confirming the current deployment model is a single worker process, single event loop, shared by every concurrent user. That's important for the blast-radius part of this answer. Here's the full breakdown, no code changes this turn.

 Rather than using the word fund scorer or fund scorer, all that try to use the word fund IQ wherever we are trying to use it lets use the word FundIQ over fund rank fund score etc

[]POWERUP - Market insights feature - idea is mostly in isntagram stories based but i feel reel like scrolling like inshorts going through news but for market insights
[]POWERUP - Portfolio vs market feature - is already built but needs to be represented in a better way Needs to be represented in a proper way on mobile using the clicky thing, like clicking it to make the change - Should be for one day, one week, one month, six months, max all these toggles and another filter that can be applied here is a comparison on the basis of value and return
[]POWERUP - Needs to be a detailed funds insights section -  Look at the app for the same
[]XIRR on the main dashboard. Getting this on the main dashboard to get fund-wise XIRR, lifetime XIRR, fund-wise, again, interchangeable clicky-wise on mobile
[]Show details, high details feature
[]1%club - section for performance consistency and risk-adjusted returns
[] A proper fund information section
[] Clickable hyperlink single page detailed fund information broker analysis AMC analysis top funds by the AMC fund manager details the other funds that they hold etc
[]Know these terms and features basically for everything there should be like an I sign or a question mark sign that should open and know these terms to help the user understand properly what the term is about
[]Update the Fund Scorer According to the copy and the UX shared by Surve
[] Return calculator section fund-wise for fund-wise mutual fund on monthly or one-time basis
[]Again, enhancing the portfolio versus market section properly
[]This is actually related to the stocks thing that we are trying to build, but Fund concentration to show how much of the fund is in mid-cap, in small cap, etc.Sector exposure of the funds, top holdings stockwise of the fund Overlapping of the fund, all these features
[]Enhanced wire calculator built according to some research done by Surve
[]A proper detailed my profile section - Both for mobile and for web app
[] Family filters across every feature, Everything that's visible on the screen, every single thing
[]Tax harvesting feature
[]Family emergency liquidity feature
[]Everything on the main dashboard and the analytics dashboard should be clickable and should have a particular perspective to it. Changes that were suggested by Darshan across this particular understanding
[]Consideration for the deletion of account. For example, someone who has used the product for 60 days wants to opt out of using it. In that situation, what to do?
[]Basic level AI integration
[]Move to Cloud and Start staging and Testing on the cloud
[]Multi-loading feature, mid-load tap switch, tap preloading both at main dashboard analytics level and family aggregate and per family member level -  In process of being built