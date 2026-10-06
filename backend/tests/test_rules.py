from app.rules import run_threshold_checks, overall_severity

def test_critical_and_missing_and_conflict():
    res = run_threshold_checks("centrifugal_pump", [
        {"sensor_name": "vibration", "value": 7.5, "unit": "mm/s"},
        {"sensor_name": "pressure", "value": 5, "unit": "bar"},
        {"sensor_name": "pressure", "value": 9, "unit": "bar"},
    ])
    by = {r["sensor"]: r["status"] for r in res}
    assert by["vibration"] == "critical"
    assert by["pressure"] == "conflict"
    assert by["temperature"] == "missing"
    assert overall_severity(res) == "critical"

def test_invalid_value():
    res = run_threshold_checks("centrifugal_pump", [{"sensor_name": "temperature", "value": 999, "unit": "C"}])
    assert [r for r in res if r["sensor"] == "temperature"][0]["status"] == "invalid"