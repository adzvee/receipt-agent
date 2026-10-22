"""Limits on login attempts, sign-ups, and demo accounts."""

from app.config import get_settings
from app.rate_limit import RateLimiter, login_per_email
from tests.factories import PASSWORD


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_allows_up_to_the_limit_then_says_how_long_to_wait():
    clock = FakeClock()
    limiter = RateLimiter("test", limit=2, window_seconds=60, clock=clock)

    assert limiter.hit("ip") is None
    clock.now += 10
    assert limiter.hit("ip") is None
    assert limiter.hit("ip") == 50  # the first hit leaves the window in 50s
    assert limiter.hit("other ip") is None  # each key is counted separately


def test_limiter_window_slides():
    clock = FakeClock()
    limiter = RateLimiter("test", limit=1, window_seconds=60, clock=clock)
    limiter.hit("ip")

    clock.now += 60

    assert limiter.hit("ip") is None


def test_login_attempts_are_limited_per_ip(anon_client, user):
    for _ in range(10):
        anon_client.post("/auth/login", json={"email": user.email, "password": "wrong guess"})

    # Blocked even with the right password, so guessing can't continue.
    response = anon_client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


def test_login_attempts_are_limited_per_email_across_ips(anon_client, user):
    # Simulate 20 attempts on this email from elsewhere.
    for _ in range(20):
        login_per_email.hit(user.email)

    response = anon_client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 429


def test_sign_ups_are_limited_per_ip(anon_client):
    statuses = [
        anon_client.post(
            "/auth/register", json={"email": f"new{n}@example.com", "password": PASSWORD}
        ).status_code
        for n in range(6)
    ]

    assert statuses == [201] * 5 + [429]


def test_demos_are_limited_per_ip(anon_client):
    statuses = [anon_client.post("/auth/demo").status_code for _ in range(6)]

    assert statuses == [201] * 5 + [429]


def test_demos_stop_when_too_many_are_active(anon_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_max_active", 1)

    assert anon_client.post("/auth/demo").status_code == 201
    busy = anon_client.post("/auth/demo")

    assert busy.status_code == 503
    assert "busy" in busy.json()["detail"]
