# Contributing

## Branches

| Branch | Purpose |
| --- | --- |
| `main` | Stable, demo-ready. Only updated from `develop` before milestones (Wk 5, 13, 18). |
| `develop` | Integration branch. All feature work merges here. |
| `feature/aeric-backend` | Aeric: API, matching engine, data |
| `feature/qizhi-frontend` | Qizhi: UI |
| `feature/lucas-ocr-ai` | Lucas: extraction pipeline |
| `feature/wesley-testing` | Wesley: tests and CI |

For a specific task, branch off your own branch or `develop`, e.g. `feature/qizhi-upload-page`.

## Daily flow

```bash
git checkout feature/<you>-<area>
git pull origin develop          # stay up to date
# ...work...
git add .
git commit -m "feat(matching): add GST check"
git push origin feature/<you>-<area>
```

Then open a pull request **into `develop`** on GitHub. At least one teammate reviews before merging.

## Commit messages

`type(scope): short summary`, where type is one of `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.

## Rules

- Never commit `.env` files, API keys or Koda's real documents. Client data is confidential.
- Put sample files you are allowed to share in `backend/app/data/`, anonymised.
- Run `pytest` before opening a PR.

