import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from bsam_agent.task_workspace import TaskWorkspace, TaskWorkspaceError


class TaskWorkspaceTests(unittest.TestCase):
    def create(self, root: Path, task_id: str = "task-001") -> TaskWorkspace:
        return TaskWorkspace.create(
            root, task_id,
            objective_sha256=hashlib.sha256(b"inspect and modify model.in").hexdigest(),
            source_scope=["model.in"],
        )

    def test_create_open_and_manifest_are_bounded_and_strict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(b"model")
            workspace = self.create(root)
            manifest = workspace.manifest()
            reopened = TaskWorkspace.open(root, "task-001")

            self.assertEqual("active", manifest["state"])
            self.assertEqual(["model.in"], manifest["source_scope"])
            self.assertEqual(manifest, reopened.manifest())
            self.assertEqual(
                root / ".bsam-agent" / "tasks" / "task-001",
                workspace.root,
            )
            with self.assertRaisesRegex(TaskWorkspaceError, "already exists"):
                self.create(root)

    def test_resolver_rejects_escape_absolute_and_symlink_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(b"model")
            workspace = self.create(root)
            for path in ("../model.in", str((root / "model.in").resolve())):
                with self.subTest(path=path), self.assertRaises(TaskWorkspaceError) as caught:
                    workspace.resolve(path)
                self.assertEqual("path_not_allowed", caught.exception.code)

            link = workspace.root / "variants" / "escape"
            try:
                os.symlink(root / "model.in", link)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable")
            with self.assertRaises(TaskWorkspaceError) as caught:
                workspace.resolve("variants/escape", must_exist=True)
            self.assertEqual("path_not_allowed", caught.exception.code)

    def test_stage_select_and_promote_is_confirmed_digest_bound_and_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(b"source")
            workspace = self.create(root)
            artifact = workspace.write_artifact(
                "variants", "candidate.in", b"candidate", media_type="text/plain",
            )
            selected = workspace.select_artifact(artifact["artifact_id"])

            self.assertEqual("selected", selected["state"])
            with self.assertRaises(TaskWorkspaceError) as caught:
                workspace.promote_selected("final.in", confirm=False)
            self.assertEqual("confirmation_required", caught.exception.code)

            promotion = workspace.promote_selected("final.in", confirm=True)
            manifest = workspace.manifest()
            self.assertEqual(b"candidate", (root / "final.in").read_bytes())
            self.assertEqual("completed", promotion["state"])
            self.assertEqual("promoted", manifest["state"])
            self.assertEqual("promoted", manifest["artifacts"][0]["state"])
            self.assertEqual(
                hashlib.sha256(b"candidate").hexdigest(), promotion["sha256"],
            )

    def test_registers_artifact_created_by_a_deterministic_task_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(b"source")
            workspace = self.create(root)
            workspace.resolve("plans/change.json").write_bytes(b'{"plan":true}')

            artifact = workspace.register_artifact(
                "plans", "change.json", media_type="application/json",
            )

            self.assertEqual("plans/change.json", artifact["path"])
            self.assertEqual("application/json", artifact["media_type"])
            with self.assertRaises(TaskWorkspaceError) as caught:
                workspace.register_artifact("plans", "change.json")
            self.assertEqual("artifact_exists", caught.exception.code)

    def test_promotion_refuses_existing_or_internal_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(b"source")
            (root / "occupied.in").write_bytes(b"keep")
            workspace = self.create(root)
            artifact = workspace.write_artifact("variants", "candidate.in", b"candidate")
            workspace.select_artifact(artifact["artifact_id"])

            with self.assertRaises(TaskWorkspaceError) as caught:
                workspace.promote_selected("occupied.in", confirm=True)
            self.assertEqual("output_exists", caught.exception.code)
            self.assertEqual(b"keep", (root / "occupied.in").read_bytes())
            with self.assertRaises(TaskWorkspaceError) as caught:
                workspace.promote_selected(
                    ".bsam-agent/tasks/task-001/variants/export.in", confirm=True,
                )
            self.assertEqual("path_not_allowed", caught.exception.code)

    def test_stale_selected_artifact_cannot_be_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(b"source")
            workspace = self.create(root)
            artifact = workspace.write_artifact("variants", "candidate.in", b"candidate")
            workspace.select_artifact(artifact["artifact_id"])
            workspace.resolve("variants/candidate.in").write_bytes(b"tampered")

            with self.assertRaises(TaskWorkspaceError) as caught:
                workspace.promote_selected("final.in", confirm=True)
            self.assertEqual("stale_artifact", caught.exception.code)
            self.assertFalse((root / "final.in").exists())

    def test_discard_removes_only_registered_task_artifacts_and_preserves_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            source.write_bytes(b"user source")
            workspace = self.create(root)
            first = workspace.write_artifact("plans", "change.json", b"{}")
            workspace.write_artifact("variants", "candidate.in", b"candidate")
            workspace.select_artifact(first["artifact_id"])
            manifest = workspace.discard_workspace()

            self.assertEqual("discarded", manifest["state"])
            self.assertTrue(workspace.manifest_path.is_file())
            self.assertEqual(b"user source", source.read_bytes())
            self.assertFalse(workspace.resolve("plans/change.json").exists())
            self.assertFalse(workspace.resolve("variants/candidate.in").exists())

    def test_corrupt_manifest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(b"source")
            workspace = self.create(root)
            value = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
            value["state"] = "unknown"
            workspace.manifest_path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaises(TaskWorkspaceError) as caught:
                workspace.manifest()
            self.assertEqual("invalid_manifest", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
