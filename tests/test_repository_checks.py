from __future__ import annotations

import json
import unittest

from tools import registry_tools, repository_checks


class RepositoryChecksTests(unittest.TestCase):
    def test_repository_contracts_are_current_without_private_source(self) -> None:
        result = repository_checks.check_repository(source_root=None)
        registry = registry_tools.load_registry(registry_tools.DEFAULT_REGISTRY)
        self.assertEqual(registry["registry_version"], result["registry_version"])
        self.assertEqual(2, result["generated_artifacts"])
        self.assertEqual("skipped-source-unavailable", result["live_source_dispatch"])
        self.assertEqual(5, len(result["required_checks"]))

    def test_committed_dispatch_token_drift_is_rejected(self) -> None:
        registry = registry_tools.load_registry(registry_tools.DEFAULT_REGISTRY)
        text = repository_checks.DEFAULT_DISPATCH_AUDIT.read_text(encoding="utf-8")
        with self.assertRaisesRegex(
            repository_checks.RepositoryCheckError, "tokens differ"
        ):
            repository_checks.validate_committed_dispatch(
                registry, text.replace("| `*TYPE` |", "| `*TYPO` |", 1),
            )

    def test_schema_root_is_bound_to_registry(self) -> None:
        registry = registry_tools.load_registry(registry_tools.DEFAULT_REGISTRY)
        schema = json.loads(
            repository_checks.DEFAULT_SCHEMA.read_text(encoding="utf-8")
        )
        repository_checks.validate_schema_binding(registry, schema)
        schema["properties"]["schema_version"]["const"] = "0.0.0"
        with self.assertRaisesRegex(
            repository_checks.RepositoryCheckError, "versions differ"
        ):
            repository_checks.validate_schema_binding(registry, schema)


if __name__ == "__main__":
    unittest.main()
