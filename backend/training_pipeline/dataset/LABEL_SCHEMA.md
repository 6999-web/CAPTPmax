# Dataset Label Schema

## Object Detection Labels

- `pistol`
- `magazine`
- `ejection_port`
- `safety_switch`

## Pose / Rule Annotations

- `is_isosceles_triangle` (bool)
- `knee_bend_angle_left` (float)
- `knee_bend_angle_right` (float)
- `feet_width_ratio` (float, feet_width / shoulder_width)
- `thumb_parallel_ok` (bool)
- `safe_muzzle_zone` (bool)

## Sequence Labels

Workflow chain:

- `A_RECEIVE_WEAPON`
- `B_INITIAL_CHECK` (required: `remove_mag -> check_chamber -> safe_on`)
- `C_PREPARE_FIRE` (required: `insert_mag -> holster_or_ready -> iso_grip -> rack_slide`)
- `D_FIRE` (required: `fire`)
- `E_FINAL_CHECK` (required: `final_remove_mag -> final_check_chamber`)

Incorrect sequence examples should explicitly mark:

- `FINAL_ORDER_ERROR`
- `ORDER_ERROR`
