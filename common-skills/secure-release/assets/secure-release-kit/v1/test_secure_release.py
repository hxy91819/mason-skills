#!/usr/bin/env python3
"""Observable-behavior tests for secure-release kit v1.

Definition:
  Exercise the public CLI in isolated Git repositories with a fake npm binary;
  no registry, credentials, or live repository is touched.

Parameters:
  Standard unittest parameters are supported.

Outputs:
  unittest results on stdout/stderr and a nonzero exit on failure.

Examples:
  python3 test_secure_release.py
  python3 -m unittest -v test_secure_release.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("secure_release.py")


class SecureReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="secure-release-test-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Release Test")
        self.git("config", "user.email", "release@example.invalid")
        (self.repo / "tracked.txt").write_text("release\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "-qm", "initial")
        self.git("branch", "-M", "main")
        self.git("-c", "tag.gpgSign=false", "tag", "v1.2.3")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.check_output(("git", *args), cwd=self.repo, text=True).strip()

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (sys.executable, str(SCRIPT), *args),
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_source_accepts_exact_reachable_tag_and_rejects_version_drift(self) -> None:
        result = self.cli(
            "source", "--tag", "v1.2.3", "--version", "1.2.3", "--primary-ref", "main"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        drift = self.cli(
            "source", "--tag", "v1.2.3", "--version", "1.2.4", "--primary-ref", "main"
        )
        self.assertNotEqual(drift.returncode, 0)
        self.assertIn("does not match", drift.stderr)

    def test_manifest_detects_changed_and_extra_artifacts(self) -> None:
        release = self.repo / "release"
        release.mkdir()
        artifact = release / "package.tgz"
        artifact.write_bytes(b"exact bytes")
        manifest = release / "manifest.json"
        created = self.cli(
            "manifest-create",
            "--tag",
            "v1.2.3",
            "--version",
            "1.2.3",
            "--artifact",
            str(artifact),
            "--output",
            str(manifest),
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        verified = self.cli(
            "manifest-verify", "--manifest", str(manifest), "--directory", str(release)
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)
        artifact.write_bytes(b"changed")
        changed = self.cli(
            "manifest-verify", "--manifest", str(manifest), "--directory", str(release)
        )
        self.assertNotEqual(changed.returncode, 0)
        artifact.write_bytes(b"exact bytes")
        (release / ".unexpected").write_text("no\n", encoding="utf-8")
        extra = self.cli(
            "manifest-verify", "--manifest", str(manifest), "--directory", str(release)
        )
        self.assertNotEqual(extra.returncode, 0)
        self.assertIn("artifact set mismatch", extra.stderr)

    def test_changelog_extracts_only_exact_tag_section(self) -> None:
        changelog = self.repo / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## v1.2.3\n\n- Current.\n\n## v1.2.2\n\n- Previous.\n",
            encoding="utf-8",
        )
        notes = self.repo / "release" / "notes.md"
        result = self.cli(
            "changelog", "--tag", "v1.2.3", "--changelog", str(changelog), "--notes", str(notes)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(notes.read_text(encoding="utf-8"), "## v1.2.3\n\n- Current.\n")

    def test_npm_pack_moves_one_tarball_and_creates_manifest(self) -> None:
        package = self.repo / "package"
        package.mkdir()
        (package / "package.json").write_text(
            json.dumps({"name": "fixture-package", "version": "1.2.3"}), encoding="utf-8"
        )
        fake_npm = self.root / "npm"
        fake_npm.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "destination=''\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"$1\" = '--pack-destination' ]; then destination=$2; shift 2; else shift; fi\n"
            "done\n"
            "printf 'packed bytes' > \"$destination/fixture-package-1.2.3.tgz\"\n"
            "printf '{\"fixture-package\":{\"filename\":\"fixture-package-1.2.3.tgz\"}}\\n'\n",
            encoding="utf-8",
        )
        fake_npm.chmod(0o755)
        release = self.repo / "release"
        result = self.cli(
            "npm-pack",
            "--tag",
            "v1.2.3",
            "--package-dir",
            str(package),
            "--output-dir",
            str(release),
            "--manifest",
            str(release / "manifest.json"),
            "--npm",
            str(fake_npm),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((release / "fixture-package-1.2.3.tgz").is_file())
        manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in manifest["artifacts"]], ["fixture-package-1.2.3.tgz"])

    def test_npm_pack_rejects_multiple_package_records(self) -> None:
        package = self.repo / "package"
        package.mkdir()
        (package / "package.json").write_text(
            json.dumps({"name": "fixture-package", "version": "1.2.3"}), encoding="utf-8"
        )
        fake_npm = self.root / "npm-multiple"
        fake_npm.write_text(
            "#!/bin/sh\n"
            "printf '{\"one\":{\"filename\":\"one.tgz\"},\"two\":{\"filename\":\"two.tgz\"}}\\n'\n",
            encoding="utf-8",
        )
        fake_npm.chmod(0o755)
        release = self.repo / "release"
        result = self.cli(
            "npm-pack",
            "--tag",
            "v1.2.3",
            "--package-dir",
            str(package),
            "--output-dir",
            str(release),
            "--manifest",
            str(release / "manifest.json"),
            "--npm",
            str(fake_npm),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must produce exactly one package", result.stderr)

    def test_registry_absence_fails_closed_on_non_404(self) -> None:
        fake_npm = self.root / "npm-error"
        fake_npm.write_text("#!/bin/sh\necho 'network timeout' >&2\nexit 1\n", encoding="utf-8")
        fake_npm.chmod(0o755)
        result = self.cli(
            "npm-absent",
            "--package",
            "fixture-package",
            "--version",
            "1.2.3",
            "--npm",
            str(fake_npm),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absence is unproven", result.stderr)

        fake_npm.write_text(
            "#!/bin/sh\necho 'upstream mentioned E404 but timed out' >&2\nexit 1\n",
            encoding="utf-8",
        )
        incidental = self.cli(
            "npm-absent",
            "--package",
            "fixture-package",
            "--version",
            "1.2.3",
            "--npm",
            str(fake_npm),
        )
        self.assertNotEqual(incidental.returncode, 0)
        self.assertIn("absence is unproven", incidental.stderr)

        fake_npm.write_text(
            "#!/bin/sh\necho 'npm error code E404' >&2\nexit 1\n", encoding="utf-8"
        )
        absent = self.cli(
            "npm-absent",
            "--package",
            "fixture-package",
            "--version",
            "1.2.3",
            "--npm",
            str(fake_npm),
        )
        self.assertEqual(absent.returncode, 0, absent.stderr)

    def test_existing_registry_version_requires_identical_tarball_bytes(self) -> None:
        artifact = self.repo / "intended.tgz"
        artifact.write_bytes(b"published bytes")
        fake_npm = self.root / "npm-existing"
        fake_npm.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "destination=''\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"$1\" = '--pack-destination' ]; then destination=$2; shift 2; else shift; fi\n"
            "done\n"
            "printf 'published bytes' > \"$destination/downloaded.tgz\"\n"
            "printf '{\"fixture-package\":{\"filename\":\"downloaded.tgz\"}}\\n'\n",
            encoding="utf-8",
        )
        fake_npm.chmod(0o755)
        matched = self.cli(
            "npm-existing",
            "--package",
            "fixture-package",
            "--version",
            "1.2.3",
            "--artifact",
            str(artifact),
            "--npm",
            str(fake_npm),
        )
        self.assertEqual(matched.returncode, 0, matched.stderr)
        artifact.write_bytes(b"different bytes")
        mismatched = self.cli(
            "npm-existing",
            "--package",
            "fixture-package",
            "--version",
            "1.2.3",
            "--artifact",
            str(artifact),
            "--npm",
            str(fake_npm),
        )
        self.assertNotEqual(mismatched.returncode, 0)
        self.assertIn("differ", mismatched.stderr)

    def test_existing_registry_version_rejects_multiple_package_records(self) -> None:
        artifact = self.repo / "intended.tgz"
        artifact.write_bytes(b"published bytes")
        fake_npm = self.root / "npm-existing-multiple"
        fake_npm.write_text(
            "#!/bin/sh\n"
            "printf '{\"one\":{\"filename\":\"one.tgz\"},\"two\":{\"filename\":\"two.tgz\"}}\\n'\n",
            encoding="utf-8",
        )
        fake_npm.chmod(0o755)
        result = self.cli(
            "npm-existing",
            "--package",
            "fixture-package",
            "--version",
            "1.2.3",
            "--artifact",
            str(artifact),
            "--npm",
            str(fake_npm),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must produce exactly one package", result.stderr)

    def test_npm_publish_uses_exact_tarball_and_provenance(self) -> None:
        artifact = self.repo / "intended.tgz"
        artifact.write_bytes(b"publish bytes")
        arguments = self.root / "publish-arguments"
        fake_npm = self.root / "npm-publish"
        fake_npm.write_text(
            f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{arguments}'\n", encoding="utf-8"
        )
        fake_npm.chmod(0o755)
        result = self.cli("npm-publish", "--artifact", str(artifact), "--npm", str(fake_npm))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            arguments.read_text(encoding="utf-8").splitlines(),
            [
                "publish",
                str(artifact),
                "--access",
                "public",
                "--tag",
                "latest",
                "--provenance",
                "--registry",
                "https://registry.npmjs.org/",
            ],
        )

    def test_npm_smoke_resolves_and_installs_exact_version(self) -> None:
        fake_npm = self.root / "npm-smoke"
        fake_npm.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "case \"$1\" in\n"
            "  view) echo '1.2.3' ;;\n"
            "  init) printf '{\"name\":\"consumer\",\"version\":\"1.0.0\"}' > package.json ;;\n"
            "  install)\n"
            "    mkdir -p node_modules/fixture-package\n"
            "    printf '{\"name\":\"fixture-package\",\"version\":\"1.2.3\"}' "
            "> node_modules/fixture-package/package.json\n"
            "    ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_npm.chmod(0o755)
        result = self.cli(
            "npm-smoke",
            "--package",
            "fixture-package",
            "--version",
            "1.2.3",
            "--npm",
            str(fake_npm),
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
