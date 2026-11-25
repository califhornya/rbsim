"""The parity tests with Python fix the historical rules 6427b90 (decision of
25/11); the tests of the corrected profile name it explicitly."""
import pytest


@pytest.fixture(autouse=True)
def _regole_storiche(monkeypatch):
    monkeypatch.setenv("RBSIM_REGOLE", "6427b90")
