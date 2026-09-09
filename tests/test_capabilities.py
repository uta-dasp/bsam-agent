from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import ApiError, LocalAgentApi
from bsam_agent.capabilities import capability_manifest
from bsam_agent.provider import ProviderConfig
from bsam_agent.orchestrator import ChatOrchestrator, capability_applicability, relevant_tools
from bsam_agent.source_set import SourceSet


def boundary_deck(convergence: bytes) -> bytes:
    return (
        b"INPUT\n3\nEND INPUT\n"
        b"BOUNDARY\n*type\nmechanical\n"
        b"*boundary condition\ntype=off, name=idle\n"
        b"*loading sequence\ntype=Static, nstep=1, incr=1\n"
        b"*convergence\n" + convergence +
        b"END BOUNDARY\n"
        b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
        b"MATERIALS\n0\nEND MATERIALS\n"
        b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
    )


def structural_deck() -> bytes:
    return boundary_deck(b"d_reduction=0.5\n").replace(
        b"*type\nsolid\n*STOP",
        b"*type\nsolid\n*NAME\nply1\n"
        b"*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n5,2,2,2\n"
        b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n*NSET,NSET=corner\n1,2\n*STOP",
    )


class NoCallProvider:
    def __init__(self) -> None:
        self.requests = []

    def complete(self, request):  # pragma: no cover - a call is a test failure
        self.requests.append(request)
        raise AssertionError("deterministic capability routing should not call the provider")


def provider_config() -> ProviderConfig:
    return ProviderConfig("fake", "fake", "http://127.0.0.1", None, 1, 10000, 128, "local-only")


class CapabilitySliceTests(unittest.TestCase):
    def test_specification_and_operational_maturity_are_separate(self) -> None:
        convergence = next(
            item for item in capability_manifest()
            if item["id"] == "construct.boundary-convergence"
        )
        self.assertEqual("documented", convergence["specification_maturity"])
        self.assertEqual("verified", convergence["operations"]["modify"])
        self.assertEqual("unsupported", convergence["operations"]["create"])
        self.assertEqual(
            [{
                "name": "maxiterations",
                "operations": {"insert": "verified", "remove": "verified"},
            }],
            convergence["parameter_edits"],
        )
        unassessed = next(
            item for item in capability_manifest() if item["id"] == "block.crack"
        )
        self.assertEqual("unassessed", unassessed["operations"]["modify"])

    def test_registry_generates_high_level_intent_support_and_applicability(self) -> None:
        constitutive = next(
            item for item in capability_manifest() if item["id"] == "block.constitutive"
        )
        self.assertEqual("verified", constitutive["intents"]["inspect"])
        self.assertEqual("verified", constitutive["intents"]["query"])
        self.assertEqual("unsupported", constitutive["intents"]["modify"])
        matched = capability_applicability("List the constitutive laws in model.in")
        self.assertEqual(
            {"block.constitutive", "command.constitutive"},
            {item["id"] for item in matched},
        )
        self.assertEqual(("query_model", "inspect_model"), relevant_tools(
            "List the constitutive laws in model.in"
        ))
        self.assertEqual(("query_model", "inspect_model"), relevant_tools(
            "Describe the constitutive definitions in model.in"
        ))
        self.assertEqual(
            ("preview_parameter_change", "preview_modify_entity"),
            relevant_tools("Increase the solver thread count in model.in to 4"),
        )
        self.assertEqual(
            ("preview_create_entity",),
            relevant_tools("Append a mesh node to model.in"),
        )
        self.assertEqual(
            ("query_model", "inspect_model"),
            relevant_tools("List nodal loads in model.in"),
        )
        self.assertEqual(
            ("preview_parameter_change", "preview_modify_entity"),
            relevant_tools("Change the nodal load target in model.in"),
        )

    def test_registry_driven_boundary_semantics_preserve_values_and_locations(self) -> None:
        raw = boundary_deck(b"rela=0.01, absolute=2\nd_reduction=0.5\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            source_set = SourceSet.read(path)
            inspection = source_set.inspection()
            rendered = source_set.render_files()[path.resolve()]
        records = inspection["semantic_model"]["capability_records"]
        convergence = next(
            item for item in records
            if item["capability_id"] == "construct.boundary-convergence"
        )
        self.assertEqual("0.01", convergence["parameters"]["relative"][0]["value"])
        self.assertEqual("rela", convergence["parameters"]["relative"][0]["spelling"])
        self.assertEqual(12, convergence["parameters"]["relative"][0]["location"]["line"])
        self.assertEqual(raw, rendered)
        self.assertTrue(inspection["no_op_round_trip"])

    def test_registry_parameter_terms_route_paraphrased_change_without_provider(self) -> None:
        provider = NoCallProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(boundary_deck(b"d_reduction=0.5\n"))
            agent = ChatOrchestrator(provider, provider_config(), LocalAgentApi(root))
            result = agent.turn(
                "Change the time increment reduction ratio in model.in to 0.4 and "
                "create a new output deck."
            )

        self.assertEqual([], provider.requests)
        self.assertEqual("preview_parameter_change", result.tool)
        self.assertEqual("confirm", result.phase)
        self.assertIn("d_reduction=0.4", result.tool_result["source_diff"])

    def test_registry_entity_terms_disambiguate_nodes_from_node_sets(self) -> None:
        provider = NoCallProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(structural_deck())
            listed = ChatOrchestrator(
                provider, provider_config(), LocalAgentApi(root),
            ).turn("List node sets in model.in.")
            referenced = ChatOrchestrator(
                provider, provider_config(), LocalAgentApi(root),
            ).turn("Show references to node 1 in model.in.")

        self.assertEqual([], provider.requests)
        self.assertTrue(all(
            item["kind"] == "node-set" for item in listed.tool_result["matches"]
        ))
        self.assertGreaterEqual(referenced.tool_result["summary"]["matches"], 1)

    def test_registry_entity_terms_expose_nodal_load_queries(self) -> None:
        provider = NoCallProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(structural_deck().replace(
                b"*STOP", b"*LOAD\n2,1,5\n*STOP",
            ))
            result = ChatOrchestrator(
                provider, provider_config(), LocalAgentApi(root),
            ).turn("List nodal loads in model.in")

        self.assertEqual([], provider.requests)
        self.assertEqual("query_model", result.tool)
        self.assertEqual("nodal-load", result.tool_result["matches"][0]["kind"])

    def test_static_validation_uses_registered_convergence_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(boundary_deck(b"relative=-1\nmaxiterations=not-an-int\nD_AA=4\n"))
            inspection = SourceSet.read(path).inspection()
        errors = [item for item in inspection["diagnostics"] if item["code"] == "BSAM-E310"]
        self.assertEqual(3, len(errors))
        self.assertEqual(3, inspection["summary"]["errors"])

    def test_focused_api_queries_report_values_defaults_and_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(boundary_deck(b"d_reduction=0.5\n"))
            api = LocalAgentApi(root)
            explicit = api.dispatch("query_model", {
                "source": "model.in", "query": "get-parameter",
                "capability": "construct.boundary-convergence", "parameter": "d_reduction",
            })
            default = api.dispatch("query_model", {
                "source": "model.in", "query": "get-parameter",
                "capability": "CONVERGENCE", "parameter": "absolute",
            })
            ambiguous = api.dispatch("query_model", {
                "source": "model.in", "query": "get-parameter", "parameter": "type",
            })
        self.assertEqual("0.5", explicit["matches"][0]["values"][0]["value"])
        self.assertEqual("registered-default", default["matches"][0]["effective_source"])
        self.assertEqual(100000000, default["matches"][0]["default"])
        self.assertTrue(ambiguous["summary"]["ambiguous"])
        self.assertEqual({"*BOUNDARY CONDITION", "*LOADING SEQUENCE"}, {
            item["canonical"] for item in ambiguous["matches"]
        })

    def test_generic_edit_accepts_canonical_capability_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(boundary_deck(b"d_reduction=0.5\n"))
            plan = LocalAgentApi(root).dispatch("preview_parameter_change", {
                "source": "model.in", "block": "BOUNDARY",
                "construct": "construct.boundary-convergence",
                "parameter": "d_reduction", "value": "0.4", "plan_path": "change.json",
            })
        self.assertEqual("*CONVERGENCE", plan["selector"]["construct"])
        self.assertEqual("0.4", plan["patch"]["new"])
        self.assertEqual(0, plan["validation"]["summary"]["errors"])

    def test_generic_rename_refuses_unverified_capability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(boundary_deck(b"d_reduction=0.5\n"))
            with self.assertRaisesRegex(ApiError, "rename is unsupported"):
                LocalAgentApi(root).dispatch("preview_rename_entity", {
                    "source": "model.in", "capability": "construct.boundary-convergence",
                    "entity_name": "one", "new_name": "two", "plan_path": "rename.json",
                })

    def test_generic_structural_adapters_are_capability_gated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(structural_deck())
            api = LocalAgentApi(root)
            node = api.dispatch("preview_create_entity", {
                "source": "model.in", "capability": "command.node",
                "attributes": {
                    "cluster": "ply1", "label": 6, "x": "3", "y": "4", "z": "5",
                },
                "plan_path": "node.json",
            })
            element = api.dispatch("preview_create_entity", {
                "source": "model.in", "capability": "command.element",
                "attributes": {
                    "cluster": "ply1", "label": 2, "element_type": "C3D4",
                    "node_labels": [1, 2, 3, 4],
                },
                "plan_path": "element.json",
            })
            node_set = api.dispatch("preview_create_entity", {
                "source": "model.in", "capability": "command.nset",
                "attributes": {"cluster": "ply1", "name": "edge", "members": [1, 2]},
                "plan_path": "set.json",
            })
            extend = api.dispatch("preview_modify_entity", {
                "source": "model.in", "capability": "command.nset",
                "entity_name": "corner",
                "changes": {"cluster": "ply1", "add_members": [3]},
                "plan_path": "extend.json",
            })
            remove_member = api.dispatch("preview_modify_entity", {
                "source": "model.in", "capability": "command.nset",
                "entity_name": "corner",
                "changes": {"cluster": "ply1", "remove_member": 2},
                "plan_path": "remove-member.json",
            })
            nodal_source = structural_deck().replace(
                b"*STOP", b"*BOUNDARY\n1,1,1,0\n*LOAD\n2,1,5\n*STOP",
            )
            (root / "nodal.in").write_bytes(nodal_source)
            retarget = api.dispatch("preview_modify_entity", {
                "source": "nodal.in", "capability": "command.load",
                "entity_name": "2",
                "changes": {"cluster": "ply1", "new_target": "corner"},
                "plan_path": "retarget.json",
            })
            coordinate_source = structural_deck().replace(
                b"*STOP",
                b"*NSET,NSET=other\n3\n*SHIFT,NSET=corner\n1,0,0\n*STOP",
            )
            (root / "coordinate.in").write_bytes(coordinate_source)
            coordinate = api.dispatch("preview_modify_entity", {
                "source": "coordinate.in", "capability": "command.shift",
                "entity_name": "corner",
                "changes": {"cluster": "ply1", "new_target": "other"},
                "plan_path": "coordinate.json",
            })
            section_source = structural_deck().replace(
                b"*STOP",
                b"*ELSET,ELSET=first\n1\n*ELSET,ELSET=second\n1\n"
                b"*SECTION,ELSET=first,LAYERS=1\n1,1\n*STOP",
            )
            (root / "section.in").write_bytes(section_source)
            retarget_section = api.dispatch("preview_modify_entity", {
                "source": "section.in", "capability": "command.section",
                "entity_name": "first",
                "changes": {"cluster": "ply1", "new_target": "second"},
                "plan_path": "retarget-section.json",
            })
            delete = api.dispatch("preview_delete_entity", {
                "source": "model.in", "capability": "command.node", "entity_name": "5",
                "context": {"cluster": "ply1"}, "plan_path": "delete.json",
            })
            delete_element = api.dispatch("preview_delete_entity", {
                "source": "model.in", "capability": "command.element",
                "entity_name": "1", "context": {"cluster": "ply1"},
                "plan_path": "delete-element.json",
            })
            delete_set = api.dispatch("preview_delete_entity", {
                "source": "model.in", "capability": "command.nset",
                "entity_name": "corner", "context": {"cluster": "ply1"},
                "plan_path": "delete-set.json",
            })
            with self.assertRaisesRegex(ApiError, "delete is unsupported"):
                api.dispatch("preview_delete_entity", {
                    "source": "model.in", "capability": "command.boundary",
                    "entity_name": "1", "context": {"cluster": "ply1"},
                    "plan_path": "blocked.json",
                })

        self.assertEqual("add-node", node["operation"])
        self.assertEqual("add-element", element["operation"])
        self.assertEqual("create-set", node_set["operation"])
        self.assertEqual("add-set-members", extend["operation"])
        self.assertEqual("remove-set-member", remove_member["operation"])
        self.assertEqual("retarget-nodal-record", retarget["operation"])
        self.assertEqual("retarget-coordinate-operation", coordinate["operation"])
        self.assertIn("+corner,1,5", retarget["source_diff"])
        self.assertEqual("retarget-section", retarget_section["operation"])
        self.assertIn("ELSET=second", retarget_section["source_diff"])
        self.assertEqual("delete-node", delete["operation"])
        self.assertEqual("delete-element", delete_element["operation"])
        self.assertEqual("delete-set", delete_set["operation"])
        self.assertIn("*NSET,NSET=edge", node_set["source_diff"])

    def test_plan_refresh_requires_a_stale_matching_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = boundary_deck(b"d_reduction=0.5\n")
            (root / "model.in").write_bytes(raw)
            (root / "other.in").write_bytes(raw)
            api = LocalAgentApi(root)
            api.dispatch("preview_parameter_change", {
                "source": "model.in", "block": "BOUNDARY", "construct": "CONVERGENCE",
                "parameter": "d_reduction", "value": "0.4", "plan_path": "change.json",
            })
            with self.assertRaisesRegex(ApiError, "not stale"):
                api.dispatch("preview_refresh_change", {
                    "source": "model.in", "stale_plan_path": "change.json",
                    "plan_path": "refreshed.json",
                })
            (root / "model.in").write_bytes(raw + b"** external change\n")
            with self.assertRaisesRegex(ApiError, "does not match"):
                api.dispatch("preview_refresh_change", {
                    "source": "other.in", "stale_plan_path": "change.json",
                    "plan_path": "wrong.json",
                })
            self.assertFalse((root / "refreshed.json").exists())
            self.assertFalse((root / "wrong.json").exists())

    def test_natural_language_query_ambiguity_and_unsupported_create_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(boundary_deck(b"d_reduction=0.5\n"))
            provider = NoCallProvider()
            agent = ChatOrchestrator(provider, provider_config(), LocalAgentApi(root))
            value = agent.turn("What is d_reduction in model.in?")
            ambiguous = agent.turn("What is type in model.in?")
            refused = agent.turn("Create a new CONVERGENCE construct in model.in.")
        self.assertEqual("query_model", value.tool)
        self.assertIn("explicitly 0.5", value.message)
        self.assertEqual("query_model", ambiguous.tool)
        self.assertIn("ambiguous", ambiguous.message)
        self.assertEqual("unsupported_capability", refused.error_code)
        self.assertIn("create is explicitly unsupported", refused.message)
        self.assertEqual([], provider.requests)


if __name__ == "__main__":
    unittest.main()
