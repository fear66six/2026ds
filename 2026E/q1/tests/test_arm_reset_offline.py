from q1.robot.safe_nexarm import Pose, pose_error


def test_pose_error_exact():
    target = Pose(200, 0, 160, -90, 0, 0)
    assert pose_error(target, target).position_mm == 0


def test_pose_error_xyz_and_orientation():
    target = Pose(200, 0, 160, -90, 0, 0)
    actual = Pose(203, 4, 160, -88, 1, 0)
    error = pose_error(actual, target)
    assert error.position_mm == 5
    assert error.pitch_deg == 2
    assert error.roll_deg == 1
