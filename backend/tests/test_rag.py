import pytest
from app.rag import retrieve, RetrievalError

def test_retrieve_vibration():
    hits = retrieve("centrifugal_pump", "high vibration and crackling noise", k=3)
    assert hits[0]["id"].startswith("PUMP-")
    assert any(h["id"] == "PUMP-2.1" for h in hits)

def test_unknown_type():
    with pytest.raises(RetrievalError):
        retrieve("steam_turbine", "vibration")

def test_no_match():
    with pytest.raises(RetrievalError):
        retrieve("centrifugal_pump", "zzzqqq")