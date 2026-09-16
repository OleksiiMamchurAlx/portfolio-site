# One authority for each kind of evidence

Canonical portfolio: [GitHub Pages](https://oleksiimamchuralx.github.io/portfolio-site/).
Other previews or experimental hosts are not independent authorities for portfolio facts.
Their content is not consumed by this build. No equivalence with an alternate host is asserted.

```text
Public project protected main (observed SHA)
  -> project.json + exact publication manifest + reviewed research
  -> portfolio_registry.json admission + pinned publication policy
  -> fetch immutable tree/blobs -> validation -> static build
  -> public receipt.json (actual deployed inputs)
```

| Data | Authority |
| --- | --- |
| Project facts and test evidence | Protected main of the admitted public project, its project.json and manifest |
| Which projects may appear | Reviewed portfolio_registry.json in this protected site repository |
| Allowed files, claims and research | Reviewed policies in this site repository, matching the project publication policy |
| Actual deployed revision and inputs | Live receipt.json and its source SHAs/content hash, checked against the uploaded artifact |
| Private telemetry and audit | Private AIQ; never a website source |

## Live resolution is fail-closed

`python tools/site.py --sync --reconcile` checks that each registered repository
is public and its main branch is reported protected by GitHub. The build resolves
each main once, then fetches the tree and every file at that exact commit. It checks
blob hashes, the exact allowlist, policy, claims and manifest before rendering.
The receipt uses those observed upstream commits, not a cached SHA or a dispatch payload.
Upstreams can advance after resolution; a later event/reconciliation picks up that change.
The receipt describes one build, not a promise that main can never advance.

A fetch failure, unprotected branch or policy mismatch stops the build. It never
falls back to an old snapshot. Cache-only or frozen builds cannot use `--reconcile`.
The deployment workflow always uses live sync. Failed checks do not replace the live site.

Protection reporting uses the [GitHub branch endpoint](https://docs.github.com/en/rest/branches/branches#get-a-branch).
This verifies `protected=true`; repository administration separately maintains the intended
PR/check/force-push/deletion rules. A boolean alone is not an audit of every ruleset.

## Generated cache is not authority

`content/projects/*.json` are explicitly labelled GENERATED SNAPSHOT / CACHE,
NOT AUTHORITATIVE with a `$comment` marker. The marker is stripped by the offline
cache reader; public `content.json` retains the existing content schema.
Snapshots may lag behind live upstream. They exist for offline previews and tests.
They are not automatically committed back by Actions and are not a second facts database.

The former `content/sources.json` is replaced by the registry. Its ambiguous
`accepted_commit` becomes `fallback_commit`: a reviewed historical revision used
only by the explicit `--sync --freeze` preview/reproduction command. Normal live
sync ignores it. Frozen/offline output must not be substituted for the deploy artifact.

The top-level source_commit and receipt source commits identify the fetched public
publication revision. `project.verification.source_commit` identifies the source
revision actually tested by the Publisher. These may legitimately differ.
`built_at` is build time; `verified_at` stays the project test time.

## Reviewed onboarding, not automatic discovery

New repositories are rejected until a PR reviews their registry entry, publication
policy, cache, schema/tests and presentation. Creating a repository alone grants
no admission. Registry/workflow changes remain reviewed; unrestricted auto-merge is off.
Future R&D stays planning-only on Reliability and QA, never the overview.

## Link verification

The existing internal link checker is unchanged. A separate anonymous HTTP checker
checks rendered HTTPS links only within the owner's GitHub namespace and canonical
Pages path. It deduplicates links, bounds time/retries, and validates redirects before
following them. Unexpected hosts, credential-bearing URLs, encoded/traversal paths,
HTTP failures and unavailable transport fail the check, not silently pass.
It checks reachability/status, not factual accuracy or every fragment anchor.

```text
python tools/check.py
python -m unittest discover -s tests -v
python tools/site.py
python tools/external_links.py --root dist
```

Both PR checks and live builds run the external-link gate. Existing rollback artifacts
and no-op suppression are retained. AIQ, Router policy, model weights and worker lifecycle
are not controlled by the site.
