# Contributing

Thanks for contributing to `tsc_print_agent`.

## Branch Model

- `main`: stable, tagged releases only.
- `develop`: next release integration branch.
- `feature/<name>`: feature work, branch from `develop`.
- `release/x.y.z`: release hardening, branch from `develop`.
- `hotfix/x.y.z`: urgent production fixes, branch from `main`.

## Pull Requests

1. Branch from the correct base (`develop` for features, `main` for hotfixes).
2. Keep PRs focused and small when possible.
3. Ensure CI is green.
4. Request at least one review before merge.

## Versioning

This project follows Semantic Versioning (`MAJOR.MINOR.PATCH`) and uses tags
on `main` like `v1.2.3`.

- `MAJOR`: breaking changes
- `MINOR`: backward-compatible features
- `PATCH`: backward-compatible fixes

## Release Steps

1. Create `release/x.y.z` from `develop`.
2. Final QA and fixes on the release branch.
3. Merge release branch into `main`.
4. Tag release on `main` as `vX.Y.Z`.
5. Merge release branch back into `develop`.
