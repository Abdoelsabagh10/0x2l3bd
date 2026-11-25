# Skills index

Skills are reusable instructions that an agent loads only when it needs them.
They live in `.opencode/skills/<id>/SKILL.md` and are discovered automatically
by OpenCode. Nothing is copied into `programs/`; every program in this
workspace shares the same library.

## How to use them

- The `description` field is the only part always visible. It tells the agent
  when the skill applies.
- An agent loads a skill with the `skill` tool, on demand, for the task at
  hand. Loading a skill is cheap, but loading all of them is not: pick one or
  two.
- A skill is reference material, never authority. Program scope
  (`programs/<program>/scope.md`), the rules in `AGENTS.md`, and an operator
  decision always win.
- Skills never authorize exploitation, scope expansion, or submission.
- Tools named inside a skill are **not** approved tools. `shared/tools.json`
  governs what may be installed or executed, and an unapproved tool stays
  unapproved no matter what a skill says.

## Imported skills

All twenty-one are adapted from
[Claude-BugHunter](https://github.com/elementalsouls/Claude-BugHunter) by
Sachin Sharma, © 2026, licensed **CC BY 4.0**. Each file carries an attribution
header stating what was modified. See `NOTICE` for the full terms.

| Skill | Purpose | Mainly useful to | Load when |
| --- | --- | --- | --- |
| `bb-methodology` | Five-phase hunting workflow and the critical-thinking framework; routes to the other skills | hunter, target-hunt | Starting a session, switching targets, or deciding what to test next |
| `hunt-idor` | Object-reference mapping, ID strategy, cross-tenant and AI-feature IDOR, impact framing | target-hunt, js-analysis | A response exposes identifiers or object-level authorization is unclear |
| `hunt-auth-bypass` | SSO/SAML assertion trust, JWT inside SSO chains, legacy endpoints | target-hunt | Login, SSO, reset, or token-trust behavior looks inconsistent |
| `hunt-oauth` | redirect_uri bypass shapes, state CSRF, nonce replay, referrer leak, deep links, token confusion, Gate 0 validation | target-hunt | The target uses OAuth/OIDC or social login, or a callback and redirect_uri are in play |
| `hunt-ato` | Taxonomy of takeover paths: reset, email change, OAuth link CSRF, MFA/session gaps, JWT, subdomain takeover at redirect_uri | target-hunt | Several weak primitives might chain into account takeover of a second test account |
| `hunt-cors` | Credentialed origin reflection, null origin, regex bypass classes, pre-flight gating, postMessage checks | target-hunt, url-triager | An endpoint returns `Access-Control-*` headers, or a SPA calls a separate API host |
| `hunt-host-header` | Reset poisoning, unkeyed cache poisoning, routing SSRF, path-override ACL bypass, OAuth issuer poisoning | target-hunt | A forgot-password flow, CDN/reverse proxy, or absolute-URL-in-email feature exists |
| `hunt-business-logic` | Coupon/race stacking, negative quantity, price overflow, client-side amount trust | target-hunt | A workflow has money, credits, quotas, or approval steps |
| `hunt-api-misconfig` | Mass assignment, prototype pollution, verb tampering, non-crypto JWT handling | target-hunt, js-analysis | API accepts extra fields, override headers, or unusual methods |
| `hunt-source-leak` | `.js.map`, Swagger/OpenAPI, `.env`/`.git`, asset manifests, secrets in chunks | js-analysis, target-hunt | Early in recon, before or alongside bundle analysis |
| `hunt-spa-api` | Recover a SPA's backend routes from its bundles, then test them unauthenticated for missing auth | js-analysis, target-hunt | A JS-heavy app, an `app`/`console`/`portal` host, or any `*api*` host appears |
| `hunt-sqli` | SQLi including ORM raw fragments, second-order, blind in resolvers | target-hunt | A parameter reaches a database through filters, search, or ordering |
| `hunt-ssrf` | Cloud metadata, DNS rebinding, gopher-to-Redis, link preview, PDF generators | target-hunt | The server fetches a URL, image, webhook, or document the user supplies |
| `hunt-file-upload` | Extension/MIME/magic-byte bypass, SVG/HTML XSS, DOCX XXE, ZIP slip, image and PDF processor SSRF | target-hunt | An upload, avatar, attachment, import, or export endpoint exists |
| `hunt-xss` | Context/encoding strategy, DOM sinks, filter bypass, impact escalation | target-hunt, js-analysis | Reflected or stored input reaches HTML, attributes, or browser sinks |
| `hunt-race-condition` | Single-packet HTTP/2, double spend, OTP and reset races, limit bypass | target-hunt | A limit, balance, or one-time action can be hit concurrently |
| `hunt-graphql` | node()/GID IDOR, mutation authz, batching and query cost, field-level authz | target-hunt, js-analysis | The target exposes `/graphql` or a GraphQL client |
| `hunt-http-smuggling` | CL.TE, TE.CL, H2.CL/H2.TE, time-delay confirmation, poisoning chains | url-triager | A CDN or reverse proxy sits in front of the origin and triage tools flag it |
| `evidence-hygiene` | Cookie/token redaction, PII masking, screenshot and filename discipline | hunter, report, all | Before any screenshot, HAR export, or evidence attachment |
| `triage-validation` | Seven-question gate, always-rejected list, CVSS 3.1 quick reference | hunter, report | Before writing or accepting any report |
| `report-writing` | Templates, impact-first wording, title and impact formulas, downgrade counters | report | After a finding passes triage, before drafting |

### Using the newer skills safely

Three points matter before acting on any of them:

- **Payload mechanics are not authorization.** `hunt-file-upload`,
  `hunt-host-header` and parts of `hunt-ato` contain concrete payloads. Running
  one is an exploitation step and needs explicit operator approval for that
  target, as `AGENTS.md` §2 requires.
- **Browser proof is mandatory** for `hunt-cors`, and out-of-band confirmation
  for the blind cases in `hunt-host-header`, `hunt-oauth` and `hunt-ato`. The
  skills say so; treat a header diff or a reflected string as a lead only.
- **Upstream cross-references are not imported.** The bodies of `hunt-ato`,
  `hunt-cors`, `hunt-file-upload`, `hunt-oauth` and `hunt-spa-api` point at
  siblings that are not in this workspace: `hunt-mfa-bypass`, `hunt-jwt-crypto`,
  `hunt-subdomain`, `hunt-saml`, `hunt-csrf`, `hunt-dom`, `hunt-tls-network`,
  `hunt-rce`, `hunt-xxe`, `hunt-nextjs`, `hunt-shadow-api`, `security-arsenal`,
  `offensive-osint`, `redteam-mindset`, `recon-scope-triage`. Do not invent
  their content; use the closest imported skill or the operator's own notes.
- `hunt-oauth` includes Android `adb`/deep-link material. It is relevant only
  when a target's mobile app is in scope; this workspace has no mobile tooling
  installed.

## Reviewed and not imported

| Skill | Reason |
| --- | --- |
| `web2-recon` | Duplicates the `sub-enum`, `urls-enum`, and `target-hunt` agents plus the deterministic `scripts/bbh` utilities. A second recon procedure would conflict with the authoritative one. |
| `recon-scope-triage` | Overlaps `AGENTS.md` §4 and `scripts/bbh/scope.py`, which are the enforced, tested source of truth for scope decisions. |
| `hunt-open-redirect` | `url-triager` already runs bounded open-redirect checks with openredirex. Revisit if manual redirect-chain testing needs the payload guidance. |
| `hunt-llm-ai` | No current program has an AI feature in scope. Import it when a target does. |

The upstream library contains 84 skills. 25 were reviewed as candidates for
this workspace; 21 were imported and 4 declined above. The remaining 59 were
not imported: most are client red-team, mobile/cloud-infrastructure, or
stack-specific material this web bug bounty workflow does not exercise, and
several duplicate the recon agents. Adding them would raise context cost
without adding a capability.

## Adding a skill

1. Read the upstream `SKILL.md` in full and check its license.
2. Copy it to `.opencode/skills/<id>/SKILL.md`.
3. Keep only `name` and `description` in the frontmatter; set `name` to the
   directory id and keep the description under 300 characters.
4. Add an attribution header naming the source, author, license, upstream URL,
   and every change you made.
5. Add a row to the table above.
6. Run `python -m unittest scripts.tests.test_config` to confirm the format is
   valid.
