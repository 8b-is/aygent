import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from create_fix_request import create_request


class DispatchTests(unittest.TestCase):
    def payload(self, **updates):
        return dict(
            feedback_id="abc-123",
            branch_name="ai-fix-abc-123",
            title="Synthetic feedback",
            **updates
        )

    def test_invalid_identifiers_never_create_files_or_run_commands(self):
        cases = [
            None,
            [],
            {},
            {"feedback_id": "../escape"},
            {"feedback_id": "-flag"},
            {"feedback_id": "a\nb"},
            {"branch_name": "main"},
            {"branch_name": "ai-fix-$(id)"},
            {"branch_name": "ai-fix-../escape"},
            {"branch_name": "ai-fix-a.lock"},
            {"title": ""},
            {"title": "a\nb"},
            {"title": "x" * 201},
            {"title": 123},
        ]
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                payload = self.payload()
                if isinstance(case, dict) and case:
                    payload.update(case)
                else:
                    payload = case
                runner = Mock()
                expected = ValueError if isinstance(payload, dict) else TypeError
                with self.assertRaises(expected):
                    create_request(payload, temp, runner)
                runner.assert_not_called()
                self.assertEqual(list(Path(temp).iterdir()), [])

    def test_existing_record_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".ai-fixes").mkdir()
            record = root / ".ai-fixes/abc-123.json"
            record.write_text("original")
            runner = Mock()
            with self.assertRaises(FileExistsError):
                create_request(self.payload(), root, runner)
            runner.assert_not_called()
            self.assertEqual(record.read_text(), "original")

    def test_directory_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as other:
            root = Path(temp)
            (root / ".ai-fixes").symlink_to(other, target_is_directory=True)
            runner = Mock()
            with self.assertRaises(ValueError):
                create_request(self.payload(), root, runner)
            runner.assert_not_called()
            self.assertEqual(list(Path(other).iterdir()), [])

    def test_title_is_literal_through_real_local_git_and_mocked_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(
                ["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "initial",
                ],
                cwd=root,
                check=True,
                capture_output=True,
            )
            title = (
                '$(touch SHOULD_NOT_EXIST) `touch ALSO_NOT_CREATED` "quoted"; & 日本語'
            )
            payload = self.payload()
            payload["title"] = title
            calls = []
            bodies = []

            def runner(args, **kwargs):
                self.assertIsInstance(args, list)
                self.assertNotIn("shell", kwargs)
                calls.append(args)
                if args[:2] == ["git", "push"]:
                    return
                if args[:3] == ["gh", "pr", "create"]:
                    bodies.append(Path(args[args.index("--body-file") + 1]).read_text())
                    return
                subprocess.run(
                    args, check=kwargs.pop("check"), **kwargs, capture_output=True
                )

            create_request(payload, root, runner)
            self.assertFalse((root / "SHOULD_NOT_EXIST").exists())
            self.assertFalse((root / "ALSO_NOT_CREATED").exists())
            self.assertEqual(
                calls[-1][calls[-1].index("--title") + 1], "[AI Fix] " + title
            )
            self.assertEqual(
                calls[-2], ["git", "push", "origin", "HEAD:refs/heads/ai-fix-abc-123"]
            )
            self.assertIn("`abc-123`", bodies[0])
            record = json.loads((root / ".ai-fixes/abc-123.json").read_text())
            self.assertEqual(record["feedback_id"], "abc-123")
            self.assertEqual(
                subprocess.check_output(
                    ["git", "branch", "--show-current"], cwd=root, text=True
                ).strip(),
                "ai-fix-abc-123",
            )
            self.assertEqual(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=root, text=True
                ),
                "",
            )


if __name__ == "__main__":
    unittest.main()
