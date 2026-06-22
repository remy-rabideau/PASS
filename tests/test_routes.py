def test_index_renders_all_controls(client):
    h = client.get("/").get_data(as_text=True)
    assert "PlanDev → ACROSS" in h
    for n in ["telescope", "instrument", "plan", "fidelity", "status", "activity_types"]:
        assert f'name="{n}"' in h
    assert "Import from ACROSS" in h
    assert "Target visibility" in h


def test_index_send_without_plan_is_graceful(client):
    h = client.post("/", data={"action": "send"}).get_data(as_text=True)
    assert h.count("Traceback") == 0
    assert "Pick a plan" in h or "Could not load" in h


def test_import_page_lists_plans(client):
    h = client.get("/import").get_data(as_text=True)
    assert "ACROSS → PlanDev" in h
    assert "Mars ACROSS Plan" in h


def test_import_writes_activities_to_plandev(client, writes):
    client.post("/import", data={
        "plan": "Mars ACROSS Plan", "ra": "56", "dec": "88", "radius": "10",
        "obs": ["0", "1"], "action": "import"})
    assert len(writes) == 2
    assert writes[0]["type"] == "ObserveTarget"
    assert "startOffset" in writes[0]
    assert "ra" in writes[0]["arguments"]


def test_import_without_plan_writes_nothing(client, writes):
    client.post("/import", data={
        "ra": "56", "dec": "88", "radius": "10", "obs": ["0"], "action": "import"})
    assert len(writes) == 0


def test_import_bad_coords_is_graceful(client):
    h = client.post("/import", data={
        "plan": "Mars ACROSS Plan", "ra": "abc", "dec": "xyz",
        "radius": "5", "action": "search"}).get_data(as_text=True)
    assert h.count("Traceback") == 0


def test_visibility_page_renders(client):
    h = client.get("/visibility").get_data(as_text=True)
    assert "Target Visibility" in h
    assert 'name="object_name"' in h
