"""Read-only four-piece planning snapshot derived from the teammate pipeline.

The teammate implementation planned all four pieces before MCU/G-code execution.
Jetson keeps its safer one-piece visual loop; this module preserves only the
useful global planning overview and never drives hardware.
"""

from __future__ import annotations

from .motion import plan_single_move


def build_four_piece_advisory(scene, mapper, config) -> dict:
    plans: list[dict] = []
    rejected: list[dict] = []
    for template_id in sorted(scene.remaining_templates):
        state = scene.templates.get(template_id)
        if state is None or state.detected_piece is None:
            rejected.append({"template_id": template_id, "reason": "piece_not_detected"})
            continue
        try:
            plan = plan_single_move(
                scene,
                template_id,
                mapper,
                config,
                reason_selected="TEAMMATE_GLOBAL_PLANNING_ADVISORY_ONLY",
            )
            plans.append(
                {
                    "template_id": template_id,
                    "source_pose_paper": plan.source_pose_paper,
                    "target_pose_paper": plan.target_pose_paper,
                    "approach_pose": plan.approach_pose,
                    "source_pose_robot": plan.source_pose_robot,
                    "rotate_pose": plan.rotate_pose,
                    "transfer_pose": plan.transfer_pose,
                    "release_pose": plan.release_pose,
                }
            )
        except (RuntimeError, ValueError) as exc:
            rejected.append({"template_id": template_id, "reason": str(exc)})
    return {
        "advisory_only": True,
        "execution_policy": "one_piece_then_home_then_visual_verify",
        "source_reference": "2026E/2026E副本/q1 pipeline -> motion.plan_motions",
        "plans": plans,
        "rejected": rejected,
    }
