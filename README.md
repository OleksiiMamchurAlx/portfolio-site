# Oleksii Mamchur — Engineering portfolio

One factual core, four views: Reliability & Automation, QA & Testing, Systems & Diagnostics, Graphics R&D.

Canonical portfolio: [GitHub Pages](https://oleksiimamchuralx.github.io/portfolio-site/).
See [Source of Truth](SOURCE_OF_TRUTH.md) and the reviewed [portfolio registry](portfolio_registry.json).

The static site reads only two public repositories, checks their exact trees and publication manifests against reviewed policy, then renders source-linked evidence. It never reads private control data or a workstation database. New claims or changed reviewed source hashes stop sync until policy review.

## Run safely

Python 3.11, standard library only:

```text
python tools/site.py
python -m unittest discover -s tests -v
python tools/site.py --sync
```

The first command builds a labelled, potentially stale cache for offline preview. It is not the live authority. Sync resolves protected public main, downloads only allowlisted public files and never executes downloaded code. Live reconciliation requires sync and cannot use cache/frozen fallback. Serve `dist` under `/portfolio-site/` to match GitHub Pages paths.

## Ownership and AI

Project owner; AI-assisted implementation, testing and documentation. I use AI tools as engineering assistants, define constraints and acceptance criteria, review outputs and validate results through reproducible evidence.

## Deployment and recovery

The Pages workflow supports public-project events, periodic reconciliation and manual recovery. Failed validation/build does not upload or deploy a replacement. Each deployment publishes a content/source receipt. The rollback workflow reuses an existing successful build artifact after review; it does not invent a past source revision.

## Limitations

Test counts are scoped to each public project, not evidence of production SRE operation. Graphics figures are synthetic, not a game benchmark. Routing superiority, model-weight training and Windows reboot recovery are not claimed. Scheduled delivery depends on GitHub scheduling and repository settings. Cross-repository event delivery requires an independently authorized transport; a repository token is not assumed to have cross-repository rights. No new employment, education, Java or full-stack claim is inferred.

## Rights

Copyright 2026 Oleksii Mamchur. Original site and project materials with AI assistance; no additional redistribution license selected. Technology names imply no affiliation. No game assets, model weights or third-party binaries are distributed.
