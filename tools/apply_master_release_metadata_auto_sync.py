from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one block in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


hardening = ROOT / ".github" / "workflows" / "release-hardening.yml"
old_hardening = '''          if [ "$target_branch" = "master" ]; then
            echo "Release metadata drift detected on master." >&2
            git diff --stat -- \\
              SOURCE_PROVENANCE.json \\
              PACKAGE_INTEGRITY_MANIFEST.json >&2
            exit 2
          fi

          if [ "$JAZN_HEAD_REPOSITORY" != "$GITHUB_REPOSITORY" ]; then
            echo "Release metadata drift cannot be committed to a fork: ${JAZN_HEAD_REPOSITORY}." >&2
            exit 2
          fi

          case "$target_branch" in
            update/*|tools/upgrade-*|hotfix/*|upgrade/*|fix/*)
              git config user.name "github-actions[bot]"
              git config user.email \\
                "41898282+github-actions[bot]@users.noreply.github.com"
              git add \\
                SOURCE_PROVENANCE.json \\
                PACKAGE_INTEGRITY_MANIFEST.json
              git commit \\
                -m "release: synchronize canonical metadata for ${runtime_version}"
              git push origin "HEAD:${target_branch}"
              ;;
            *)
              echo "Release metadata drift detected outside an allowed synchronization branch: ${target_branch}." >&2
              exit 2
              ;;
          esac
'''
new_hardening = '''          if [ "$JAZN_HEAD_REPOSITORY" != "$GITHUB_REPOSITORY" ]; then
            echo "Release metadata drift cannot be committed to a fork: ${JAZN_HEAD_REPOSITORY}." >&2
            exit 2
          fi

          case "$target_branch" in
            master|update/*|tools/upgrade-*|hotfix/*|upgrade/*|fix/*)
              git config user.name "github-actions[bot]"
              git config user.email \\
                "41898282+github-actions[bot]@users.noreply.github.com"
              git add \\
                SOURCE_PROVENANCE.json \\
                PACKAGE_INTEGRITY_MANIFEST.json
              if [ "$target_branch" = "master" ]; then
                commit_message="release: synchronize canonical metadata for ${runtime_version} [skip ci]"
              else
                commit_message="release: synchronize canonical metadata for ${runtime_version}"
              fi
              git commit -m "$commit_message"
              git push origin "HEAD:${target_branch}"
              ;;
            *)
              echo "Release metadata drift detected outside an allowed synchronization branch: ${target_branch}." >&2
              exit 2
              ;;
          esac
'''
replace_once(hardening, old_hardening, new_hardening)

metadata_sync = ROOT / ".github" / "workflows" / "release-metadata-sync.yml"
old_metadata_sync = '''          if [ "$target_branch" = "master" ]; then
            echo "Release metadata drift detected on master." >&2
            echo "Repair it on an allowed update, tools/upgrade, hotfix, upgrade or fix branch." >&2
            git diff --stat -- \\
              SOURCE_PROVENANCE.json \\
              PACKAGE_INTEGRITY_MANIFEST.json >&2
            exit 2
          fi

          if [ "$JAZN_HEAD_REPOSITORY" != "$GITHUB_REPOSITORY" ]; then
            echo "Release metadata drift cannot be committed to a fork: ${JAZN_HEAD_REPOSITORY}." >&2
            echo "Synchronize metadata in the source repository before updating this pull request." >&2
            exit 2
          fi

          case "$target_branch" in
            update/*|tools/upgrade-*|hotfix/*|upgrade/*|fix/*)
              runtime_version="$(
                python -X utf8 -c \\
                  'from latka_jazn.version import PACKAGE_VERSION_FULL; print(PACKAGE_VERSION_FULL)'
              )"

              echo "Synchronizing release metadata for ${runtime_version}."
              git config user.name "github-actions[bot]"
              git config user.email \\
                "41898282+github-actions[bot]@users.noreply.github.com"
              git add \\
                SOURCE_PROVENANCE.json \\
                PACKAGE_INTEGRITY_MANIFEST.json
              git commit \\
                -m "release: synchronize canonical metadata for ${runtime_version}"
              git push origin "HEAD:${target_branch}"
              exit 0
              ;;
          esac

          echo "Release metadata drift detected outside an allowed synchronization branch: ${target_branch}." >&2
          exit 2
'''
new_metadata_sync = '''          if [ "$JAZN_HEAD_REPOSITORY" != "$GITHUB_REPOSITORY" ]; then
            echo "Release metadata drift cannot be committed to a fork: ${JAZN_HEAD_REPOSITORY}." >&2
            echo "Synchronize metadata in the source repository before updating this pull request." >&2
            exit 2
          fi

          case "$target_branch" in
            master|update/*|tools/upgrade-*|hotfix/*|upgrade/*|fix/*)
              runtime_version="$(
                python -X utf8 -c \\
                  'from latka_jazn.version import PACKAGE_VERSION_FULL; print(PACKAGE_VERSION_FULL)'
              )"

              echo "Synchronizing release metadata for ${runtime_version}."
              git config user.name "github-actions[bot]"
              git config user.email \\
                "41898282+github-actions[bot]@users.noreply.github.com"
              git add \\
                SOURCE_PROVENANCE.json \\
                PACKAGE_INTEGRITY_MANIFEST.json
              if [ "$target_branch" = "master" ]; then
                commit_message="release: synchronize canonical metadata for ${runtime_version} [skip ci]"
              else
                commit_message="release: synchronize canonical metadata for ${runtime_version}"
              fi
              git commit -m "$commit_message"
              git push origin "HEAD:${target_branch}"
              exit 0
              ;;
          esac

          echo "Release metadata drift detected outside an allowed synchronization branch: ${target_branch}." >&2
          exit 2
'''
replace_once(metadata_sync, old_metadata_sync, new_metadata_sync)

print("master release-metadata auto-sync blocks updated")
