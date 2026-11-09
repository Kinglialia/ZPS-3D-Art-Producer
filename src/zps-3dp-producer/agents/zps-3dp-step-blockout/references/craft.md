# Craft (chép từ kit v0.10.4, `905dc93`; xem SOURCE.md)

Nguyên văn `references/blockout.md` (§A, Image evidence, Preflight) và `references/technique.md` §1–2.
Phần nói về 3D Artist, bake, LOD không áp cho Blockout.

<!-- blockout.md -->

## A. Receive the task → blockout
**Receive:** the task code (if any), the allowed write area, the source/brief/style versions, the goal, and the relevant target requirements.
1. Accept only the assigned asset or batch. Do not scan every zip on your own. Check that the file exists and opens. Check the schema, if one exists, and the data the task needs. Unpack in the allowed area. Block paths that escape the area. Do not overwrite the source or other runs. A report that exists does not mean the task is complete.
2. Read the concept package: locked parts, flexible parts, the source of measurements, verification status, hidden parts, and functional landmarks. Ask only for angles or callouts that resolve a missing part. Do not assume that 5 views or material masks are needed. One clear concept can be enough to start the blockout. Views that contradict each other are not enough, even if the count is complete. Classify each gap as one of: blocks the related build / resolve through the blockout / decide within your authority. Report the gap with a recommendation.
3. Lock the standard for units, orientation, origin, and status. Key numbers need a measurement source. Separate the main body from the cover layer and from nested or overlapping parts. A perspective image does not give real measurements. An orthographic image needs a proportion standard and consistency. Use interaction references and gameplay dimensions when they exist. Do not add assumptions and present them as approved.
4. Use the visual standard and the asset-group solution if they still fit. Read [technique](technique.md) to choose a technique or to handle a new risk. Decide the solution yourself if it stays within the standard and budget. If you change an approved way of showing something, submit it to the visual approver. A mesh from a generator must pass the same checks as a self-built mesh. Choose tools that exist and are within your authority. Keep the raw files and the provenance.
5. Build the main mass and the separate or moving parts that are needed. Identify the support faces and the important joints. Identify the construction parts that are still inferred. Measure the real size. Compare with the reference at the matching angle. View the blockout at the target camera and size, and at the allowed viewing angles, to confirm the reading priority in the brief. If the game camera does not exist yet, write "not checked". Do not call a detail important only because it appears in the concept. If you find a contradiction, record it with an option. Do not legitimize it silently.
**Handoff:** a versioned blockout, comparison images, real measurements, questions and assumptions, and a recommended next step. `Enough to start the blockout` is not the same as `Design checked in 3D`. The 3D Artist reports the evidence. The visual approver receives the art part. The owner of the functional requirement receives the matching part. Write each result correctly in the handoff report.


**Image evidence:** state which images you really opened and viewed with a tool. State which images the handoff only described. If you have not viewed an image, conclude only from the text. Do not list the image as read. Do not claim a visual comparison.

**Preflight for script builds:** set and check scene units and unit scale explicitly. Point the light and camera at the target before a diagnostic render. For a hidden part that wraps around the bottom, measure body-to-floor and accessory-to-floor separately (world bounds, cross-section, close-up angle). Do not lift the whole body to hide a part that goes through the floor. A number inferred from the concept is only an assumption to test. It is not confirmed geometry.

<!-- technique.md §1–2 -->

## 1. Analyze before you choose

Read the concept, the visual standard, the set anchor, and the task criteria. Identify the camera, the display size, the motion and interaction requirements, the engine/shader, and the known budget. If missing information affects the choice, state an assumption and its effect.

Use the reading priority in the brief. The task giver defines function and information. The visual approver defines visual features. View at the allowed angles, viewing distances, and display sizes. Do not infer importance only from the area in the concept or from an enlarged render. If information is missing, record a recommendation or an assumption. Ask only about what would change the decision.

Classify each detail by role: mass/outline; construction and joints; motion/interaction; light response; color and pattern. One detail can have several roles.

## 2. Choose a technique by its effect

| Technique | When to consider it | What to check |
|---|---|---|
| **Geometry** | The detail affects the silhouette, thickness, gaps, motion, shadow, or interaction | The shape at the needed angles; whether the quality is worth the geometry cost |
| **Bevel + custom/weighted normals** | Edges need to catch light, and large faces need stable shading | The bevel is visible enough at the target camera; it does not distort the mass or create shading faults |
| **Normal map** | The detail must change the light response but does not need real mass or gaps | It reads at the target size; tangent, UV, compression, and shader are correct |
| **Color texture/hand-painted** | Color zones, patterns, or light and dark in the style | It matches the visual language; painted lighting fits the target lighting |
| **Trim sheet/tiling** | The detail or material repeats across many surfaces or assets | Scale, pattern direction, seams, repetition, and whether the material can be shared |
| **Decal** | A symbol or local detail must be placed independently on a surface | Renderer support, layering, cost, and visibility at oblique angles |
| **Cards + alpha** | A thin form such as a leaf, hair, or a cluster of details that fits a flat plane | View angle, silhouette, shadow, mip/alpha, and overdraw; do not assume it is cheaper than geometry |
| **Parallax/POM** | The surface needs more depth than a normal map gives, and the target shader supports it | Oblique angles, artifacts, GPU cost, and limits at the edge of the object |
| **LOD** | The asset appears at many display sizes and reducing detail helps | Loss of silhouette, shading, and identifying detail, and the transition between levels; do not force a fixed reduction ratio |

Combine techniques for each part of the asset. Do not choose only from the asset type or the platform. Do not apply one depth threshold in cm to every case.

For a detail that only changes color or pattern, prefer a color texture or a material. For a detail that needs a light response but not real mass, consider a normal map. Use geometry to keep the silhouette, thickness, gaps, shadow, motion, or interaction that matters in the brief. A normal map does not replace an outline or a construction that you removed.

If you are not sure, use a small test in the existing proof step. Remove the geometry of a representative area. Replace it with a suitable texture or normal. Compare under the same camera, light, and size at the usage angles. Accept the result if it keeps the reading priority and the function. Do not conclude that the method failed only because the test map is not right. If a suitable standard or sample exists, reuse it. Do not test every scratch, and do not open an additional gate. Coordinate with the texture/material side when it exists. If you change an approved way of showing something, you must still submit it to the visual approver.
