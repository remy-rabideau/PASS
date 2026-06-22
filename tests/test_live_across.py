import pytest
import requests

import across_data

pytestmark = pytest.mark.live


def test_telescopes_load():
    tels = across_data.get_telescopes()
    assert len(tels) > 0
    assert all("instruments" in t for t in tels)


def test_cone_search_returns_observations():
    obs = across_data.get_nearby_observations(56, 88, 10, limit=5)
    assert len(obs) > 0
    assert {"ra", "dec", "begin", "object_name"} <= set(obs[0])


def test_resolve_object_m31():
    r = across_data.resolve_object("M31")
    assert abs(r["ra"] - 10.68) < 0.1
    assert abs(r["dec"] - 41.27) < 0.1


def test_visibility_windows_for_visible_instrument():
    instruments = requests.get(f"{across_data.ACROSS_API}/instrument/", timeout=30).json()
    found_windows = False
    for inst in instruments[:8]:
        try:
            w = across_data.get_visibility_windows(
                inst["id"], 10.68, 41.27, "2026-07-01T00:00:00", "2026-07-02T00:00:00")
        except requests.HTTPError:
            continue
        if w:
            assert {"begin", "end", "duration"} <= set(w[0])
            found_windows = True
            break
    assert found_windows, "no instrument returned visibility windows (ACROSS may be slow)"
