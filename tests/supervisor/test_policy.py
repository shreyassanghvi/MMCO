from mmco.supervisor.policy import RestartPolicy


def test_first_attempt_uses_base_delay():
    policy = RestartPolicy(base_s=0.5, cap_s=10.0)
    assert policy.backoff(0) == 0.5


def test_backoff_doubles_per_attempt():
    policy = RestartPolicy(base_s=0.5, cap_s=10.0)
    assert policy.backoff(1) == 1.0
    assert policy.backoff(2) == 2.0
    assert policy.backoff(3) == 4.0


def test_backoff_is_capped():
    policy = RestartPolicy(base_s=0.5, cap_s=10.0)
    assert policy.backoff(100) == 10.0
    assert policy.backoff(8) <= 10.0  # 0.5 * 256 would be 128, capped to 10
