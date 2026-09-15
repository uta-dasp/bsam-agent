# Structured model construction

The first generic substantial-construction acceptance uses
`tests/fixtures/structured_copy_source.in`. It is a non-proprietary, current-syntax model containing
one explicit C3D8 cluster named `layer1`. The associated
`structured_copy_objective.json` asks the agent to retain that cluster and construct `layer2` and
`layer3` by translating complete copies by `[0, 0, 1]` and `[0, 0, 2]`. The specialized notch-ply
tool is prohibited on this acceptance path.

## Source structure and dependency boundary

The selected cluster owns eight nodes, one C3D8 element, `bottom` and `top` node sets, the `solid`
element set, one element orientation, and one material-1 section assignment. All labels and names
inside the fixture resolve without ambiguity. The fixture deliberately has no cross-cluster
references, so the first vertical slice can prove complete internal copying and retargeting before
supporting external dependents.

A construction is applicable only when the source cluster is unique, its mesh is explicit, every
reference resolves, all destination names are unused, and every transform is finite and
nondegenerate. Unsupported or ambiguous external dependencies fail before a candidate is rendered.

## Invariants

- The original source set and `layer1` remain unchanged.
- Node and element labels remain cluster-local and are preserved in each copy.
- Element topology, cluster-local sets, section assignment, and orientation semantics are copied
  exactly and retargeted to the new cluster owner.
- The plan is bound to one source-set digest and is expanded with deterministic bounds.
- The complete physics-changing plan receives one review and confirmation boundary.
- Construction occurs in the task workspace; only the selected, validated source set is promoted
  to a collision-free project destination.
- The result must contain three clusters, 24 nodes, three C3D8 elements, six node sets, three
  element sets, three orientations, and three sections, with no static-validation errors.

## Engineering decisions

The source cluster, instance names/transforms, and any non-preserving material, section, or
orientation policy are user-approved choices. The local-label and topology/set policies are
source-derived because the registry and inspected fixture establish cluster-local ownership.
Exact-preservation instructions in the acceptance objective resolve the material, section, and
orientation choices; the agent must not ask for them again. Missing or conflicting choices trigger
focused clarification while the partial plan remains resumable.

Passing this acceptance proves deterministic construction and static compatibility. It does not
claim runtime compatibility or convergence; those require the separate smoke and full-run slices.
