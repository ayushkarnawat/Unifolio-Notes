# An AWS account is created, and the domain moves from GoDaddy to Route 53

## For stakeholders

Before any real infrastructure could be built, the product needed an actual
AWS account and a real domain pointed at AWS instead of the previous
registrar. Both were set up with standard security basics from day one
(a spending alert, multi-factor authentication on the account's root user),
and the site's mail — which runs on a separate provider — was carried over
without disruption. The three-domain shape decided here (a marketing site,
a production app, and a staging app, each on its own subdomain) is the
naming scheme every AWS resource built afterward follows.

## Technical detail

### Intended outcome

Stand up a real AWS account, confirm the deployment region, and move
`unifolio.in`'s DNS to a Route 53-hosted zone so subsequent Terraform work
has real infrastructure to target.

### What actually happened

An AWS account was created with root-user MFA and a $50 budget alert. A
dedicated IAM admin user was created for day-to-day work (account alias and
admin username both contain uncorrected typos — noted, not yet fixed). The
deployment region was confirmed as `ap-south-1`.

`unifolio.in`'s nameservers were switched from GoDaddy to a new Route 53
public hosted zone. Eleven DNS records were audited during the cutover;
Microsoft 365's mail records (MX, SPF, DMARC, autodiscover) were carried
over unchanged so mail delivery was not disrupted, while GoDaddy-proprietary
records were dropped. Propagation was verified with `dig`/`nslookup`.

Domain architecture was decided: `unifolio.in` (apex) is the marketing
site with Login/Sign Up calls to action; `app.unifolio.in` is the
production web app; `staging.unifolio.in` is the staging web app. Backend
API domain naming (a dedicated subdomain vs. path-based CloudFront routing)
was left open, needed before HTTPS/CDN work but not before the first
Terraform apply.

A networking decision was also made ahead of the first Terraform apply:
staging uses a self-hosted **fck-nat** EC2 instance rather than a managed
NAT Gateway, specifically to avoid the cost-approval step a managed NAT
Gateway would trigger.

Before any Terraform work began, the session independently re-verified —
rather than trusting an earlier session's self-report — that a prior batch
of compliance-audit fixes (F8, the ADR-006 job scripts, and the non-PAN
duplicate-detection wiring) had in fact already been committed
(`9fe21fe`), and that every item a stale internal readiness document still
listed as an open blocker (Dockerfile, an OTP stub-mode guard, CORS,
`/imports/parse` upload validation, enum-widening migrations, the ADR-006
job scripts) was actually present in the code — the tracking document was
stale, not the code. Full suites re-ran clean: 614 backend passed (6
skipped), 397 frontend passed (75 files), `tsc -b --noEmit` clean.

### Deviation (if any) — decision or response taken

None — this stage is account/DNS setup and verification, not a design
reversal.

### Result

A real AWS account and a Route 53-hosted domain exist; the region, domain
architecture, and staging NAT approach are decided; Terraform Phase 0/1
work is unblocked. See [2026-09-09](2026-09-09-terraform-applied-and-iam-key-incident.md)
for the first real Terraform apply against this account.

### Related

- ADR-005 — deployment architecture (ECS Express Mode; this stage is the
  account this architecture runs inside)
- Evidence: `08-evidence/documents/engineering-loop/CLAUDE.md` ("Session
  State", dated 2026-09-07), `08-evidence/documents/engineering-loop/session.md`
