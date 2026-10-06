from dataclasses import dataclass, asdict


THRESHOLDS = {
    "centrifugal_pump": {
        "vibration":   {"unit": "mm/s", "warn": 4.5, "critical": 7.1, "plausible": (0, 50)},
        "temperature": {"unit": "C",    "warn": 75,  "critical": 90,  "plausible": (-20, 200)},
        "pressure":    {"unit": "bar",  "warn": 9,   "critical": 11,  "plausible": (0, 40)},
    },
    "air_compressor": {
        "temperature": {"unit": "C",    "warn": 95,  "critical": 110, "plausible": (-20, 250)},
        "pressure":    {"unit": "bar",  "warn": 9.5, "critical": 11,  "plausible": (0, 40)},
        "vibration":   {"unit": "mm/s", "warn": 5.0, "critical": 8.0, "plausible": (0, 50)},
    },
    "conveyor_motor": {
        "temperature": {"unit": "C",    "warn": 80,  "critical": 100, "plausible": (-20, 200)},
        "current":     {"unit": "A",    "warn": 28,  "critical": 35,  "plausible": (0, 200)},
        "vibration":   {"unit": "mm/s", "warn": 4.0, "critical": 6.5, "plausible": (0, 50)},
    },
}

CONFLICT_TOLERANCE = 0.10 

@dataclass
class CheckResult:
    sensor: str
    status: str            # normal | warning | critical | missing | invalid | conflict
    value: float | None
    unit: str | None
    rule: str
    message: str

def _check_value(sensor, cfg, value, unit):
    lo, hi = cfg["plausible"]
    if unit and unit != cfg["unit"]:
        return CheckResult(sensor, "invalid", value, unit, f"expected unit {cfg['unit']}",
                           f"Unit mismatch: got {unit}, expected {cfg['unit']}. Value not evaluated.")
    if not (lo <= value <= hi):
        return CheckResult(sensor, "invalid", value, unit, f"plausible range {lo}-{hi}",
                           f"{value} is outside plausible range; possible sensor fault.")
    if value >= cfg["critical"]:
        return CheckResult(sensor, "critical", value, unit, f">= {cfg['critical']} {cfg['unit']}",
                           f"{sensor} {value} {cfg['unit']} is at or above critical limit.")
    if value >= cfg["warn"]:
        return CheckResult(sensor, "warning", value, unit, f">= {cfg['warn']} {cfg['unit']}",
                           f"{sensor} {value} {cfg['unit']} is above warning limit.")
    return CheckResult(sensor, "normal", value, unit, f"< {cfg['warn']} {cfg['unit']}",
                       f"{sensor} within normal range.")

def run_threshold_checks(equipment_type: str, readings: list[dict]) -> list[dict]:
    """readings: [{"sensor_name": "vibration", "value": 7.5, "unit": "mm/s"}, ...]"""
    spec = THRESHOLDS.get(equipment_type)
    if spec is None:
        return [asdict(CheckResult("-", "invalid", None, None, "unknown equipment type",
                                   f"No threshold rules for '{equipment_type}'."))]

    by_sensor: dict[str, list[dict]] = {}
    for r in readings:
        by_sensor.setdefault(r["sensor_name"], []).append(r)

    results: list[CheckResult] = []
    for sensor, cfg in spec.items():
        rs = [r for r in by_sensor.get(sensor, []) if r.get("value") is not None]
        if not rs:
            results.append(CheckResult(sensor, "missing", None, None, "reading expected",
                                       f"No {sensor} reading provided. Not assumed normal."))
            continue
        values = [r["value"] for r in rs]
        if len(values) > 1 and (max(values) - min(values)) > CONFLICT_TOLERANCE * max(abs(v) for v in values):
            results.append(CheckResult(sensor, "conflict", None, cfg["unit"],
                                       f"readings differ > {int(CONFLICT_TOLERANCE*100)}%",
                                       f"Conflicting {sensor} readings: {values}. Not evaluated; verify sensor."))
            continue
        results.append(_check_value(sensor, cfg, values[0], rs[0].get("unit")))


    for sensor in by_sensor:
        if sensor not in spec:
            results.append(CheckResult(sensor, "invalid", None, None, "no rule defined",
                                       f"No threshold rule for '{sensor}'. Not evaluated."))
    return [asdict(r) for r in results]

def overall_severity(results: list[dict]) -> str:
    statuses = {r["status"] for r in results}
    if "critical" in statuses: return "critical"
    if "warning" in statuses:  return "warning"
    if statuses & {"missing", "invalid", "conflict"}: return "uncertain"
    return "normal"