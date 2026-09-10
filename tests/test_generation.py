from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import ApiError, LocalAgentApi


def intent() -> dict:
    return {
        "profile": "generation.mechanical-isotropic-solid-v1",
        "unit_system": "N-mm-MPa",
        "analysis": {
            "type": "mechanical", "kinematics": "linear",
            "name": "coupon_analysis", "status": "no restart",
        },
        "cluster": {"name": "coupon"},
        "solver": {"type": "pardiso", "n_threads": 2, "matrix_type": "indefinite"},
        "convergence": {
            "relative_tolerance": 1e-6, "absolute_tolerance": 1e-8,
            "divergence_tolerance": 1e6, "max_iterations": 20,
        },
        "loading": {"name": "static_load", "step_count": 1, "increment": 1.0},
        "material": {
            "youngs_modulus": 70000.0,
            "poisson_ratio": 0.3,
            "thermal_expansion": 0.000023,
            "tensile_strength": 300.0,
            "compressive_strength": 250.0,
            "shear_strength": 150.0,
        },
        "constitutive": {"failure_type": 4, "z_rotation_degrees": 0.0},
        "constraints": [{"target": "bottom", "first_dof": 1, "last_dof": 3, "value": 0.0}],
        "loads": [{"target": "top", "dof": 3, "value": 100.0}],
    }


class DeckGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        fixture = Path(__file__).parent / "fixtures" / "abaqus_style_mesh_no_surface.ele"
        (self.root / "mesh.ele").write_bytes(fixture.read_bytes())
        self.api = LocalAgentApi(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_generates_valid_canonical_deck_with_stable_provenance(self) -> None:
        first = self.api.dispatch("generate_deck", {
            "mesh": "mesh.ele", "intent": intent(), "destination": "first.in",
            "manifest": "first.generation.json", "confirm": True,
        })
        second = self.api.dispatch("generate_deck", {
            "mesh": "mesh.ele", "intent": intent(), "destination": "second.in",
            "manifest": "second.generation.json", "confirm": True,
        })
        self.assertEqual(0, first["validation"]["errors"])
        self.assertEqual(first["generation_id"], second["generation_id"])
        self.assertEqual(first["output_sha256"], second["output_sha256"])
        self.assertEqual((self.root / "first.in").read_bytes(), (self.root / "second.in").read_bytes())
        deck = (self.root / "first.in").read_text(encoding="latin-1")
        self.assertIn("** INTENT-SHA256", deck)
        self.assertIn("*type=pardiso\nn_threads=2\nmatrix_type=indefinite", deck)
        self.assertIn(
            "type=disp,comp=xyz,name=constraint1,value=0,nset=coupon.bottom", deck
        )
        self.assertIn("type=force,comp=z,name=load1,value=100,nset=coupon.top", deck)
        self.assertIn("type=Static,name=static_load,nstep=1,incr=1", deck)
        self.assertIn("relative=9.9999999999999995e-07,absolute=1e-08,divergence=1000000", deck)
        self.assertIn("*SELECTION,ID=1,TYPE=NODE\nbottom", deck)
        self.assertIn("*SELECTION,ID=2,TYPE=NODE\ntop", deck)
        self.assertLess(deck.index("*NSET,NSET=top"), deck.index("*SELECTION,ID=2,TYPE=NODE"))

    def test_requires_every_engineering_choice_and_confirmation(self) -> None:
        incomplete = copy.deepcopy(intent())
        del incomplete["material"]["youngs_modulus"]
        with self.assertRaisesRegex(ApiError, "youngs_modulus") as missing:
            self.api.dispatch("generate_deck", {
                "mesh": "mesh.ele", "intent": incomplete, "destination": "missing.in",
                "manifest": "missing.json", "confirm": True,
            })
        self.assertEqual("missing_engineering_choice", missing.exception.code)
        with self.assertRaisesRegex(ApiError, "confirm=true") as confirmation:
            self.api.dispatch("generate_deck", {
                "mesh": "mesh.ele", "intent": intent(), "destination": "unconfirmed.in",
                "manifest": "unconfirmed.json", "confirm": False,
            })
        self.assertEqual("confirmation_required", confirmation.exception.code)
        self.assertFalse((self.root / "unconfirmed.in").exists())

        unsafe_solver = copy.deepcopy(intent())
        unsafe_solver["solver"]["matrix_type"] = "definite"
        with self.assertRaisesRegex(ApiError, "matrix_type") as matrix:
            self.api.dispatch("generate_deck", {
                "mesh": "mesh.ele", "intent": unsafe_solver, "destination": "definite.in",
                "manifest": "definite.json", "confirm": True,
            })
        self.assertEqual("invalid_intent", matrix.exception.code)

    def test_rejects_unsupported_surface_and_refuses_overwrite(self) -> None:
        full = Path(__file__).parent / "fixtures" / "abaqus_style_mesh.ele"
        (self.root / "surface.ele").write_bytes(full.read_bytes())
        with self.assertRaisesRegex(ApiError, "SURFACE") as unsupported:
            self.api.dispatch("generate_deck", {
                "mesh": "surface.ele", "intent": intent(), "destination": "surface.in",
                "manifest": "surface.json", "confirm": True,
            })
        self.assertEqual("unsupported_generation", unsupported.exception.code)
        (self.root / "existing.in").write_text("keep", encoding="ascii")
        with self.assertRaises(ApiError) as existing:
            self.api.dispatch("generate_deck", {
                "mesh": "mesh.ele", "intent": intent(), "destination": "existing.in",
                "manifest": "existing.json", "confirm": True,
            })
        self.assertEqual("output_exists", existing.exception.code)
        self.assertEqual("keep", (self.root / "existing.in").read_text(encoding="ascii"))
        self.assertFalse((self.root / "existing.json").exists())


if __name__ == "__main__":
    unittest.main()
