# JavaScript / Node.js tooling boundary

Ten katalog jest opcjonalną warstwą narzędziową Jaźni. Nie zastępuje Pythonowego
rdzenia, `run.py`, pamięci, routingu ani lifecycle i nie jest wymagany do startu
portable/offline runtime.

## Kontrakt

- CI-tested runtime: Node.js 24 LTS.
- Moduły: ESM (`"type": "module"`).
- Instalacja CI: wyłącznie `npm ci` z zatwierdzonym `package-lock.json`.
- `node_modules/` jest stanem lokalnym i nigdy nie trafia do repo/paczki.
- Bieżący pakiet nie ma zależności npm; nowe zależności wymagają osobnego audytu,
  lockfile, testów Windows/Linux i uzasadnienia capability.
- Brak Node.js nie może blokować Pythonowego runtime Jaźni. Dostępność Node jest
  wykrywana przez `python -X utf8 -m latka_jazn.tools.javascript_runtime --json`.

## Walidacja

```text
npm ci --prefix tools/javascript --ignore-scripts --no-audit --no-fund
npm run --prefix tools/javascript check
npm run --prefix tools/javascript probe
python -X utf8 -m latka_jazn.tools.javascript_runtime --require-node24 --json
```

Kontrakt CI uruchamia te kontrole zarówno na `ubuntu-latest`, jak i
`windows-latest`.

## Źródła techniczne

- GitHub Actions Node 20 deprecation:
  https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
- GitHub Secure Use — full-length SHA pinning:
  https://docs.github.com/en/actions/reference/security/secure-use
- Node.js release schedule / LTS:
  https://nodejs.org/en/about/previous-releases
- npm `ci`:
  https://docs.npmjs.com/cli/commands/npm-ci/
- npm `package-lock.json`:
  https://docs.npmjs.com/files/package-lock.json/
