from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("role", ["writer", "reviewer", "approver"])
def test_app_runs_for_each_role(role):
    data = (ROOT / "samples" / "sample_proposal_fictional.xlsx").read_bytes()
    at = AppTest.from_file(str(ROOT / "Appraisal.py"), default_timeout=120)
    at.secrets["access"] = {"codes": {"writer": "w", "reviewer": "r", "approver": "a"}}
    at.session_state["role"] = role
    at.session_state["user"] = "Test user"
    at.session_state["file"] = {"name": "sample.xlsx", "data": data, "origin": "upload"}
    at.run()
    assert not at.exception
    assert not at.error


def test_sign_in_rejects_bad_code():
    at = AppTest.from_file(str(ROOT / "Appraisal.py"), default_timeout=60)
    at.secrets["access"] = {"codes": {"writer": "w", "reviewer": "r", "approver": "a"}}
    at.run()
    at.sidebar.text_input[0].input("Someone")
    at.sidebar.text_input[1].input("wrong")
    at.sidebar.button[0].click().run()
    assert at.sidebar.error and "role" not in at.session_state


def test_dashboard_renders_register():
    import runpy

    import pandas as pd

    import appraisal.sharepoint as sp_mod

    runpy.run_path(str(ROOT / "samples" / "make_demo_register.py"), run_name="__main__")
    rows = pd.read_csv(ROOT / "samples" / "demo_register.csv").to_dict("records")

    class FakeSP:
        def read_register(self):
            return rows

    orig = sp_mod.SharePointClient.from_secrets
    sp_mod.SharePointClient.from_secrets = classmethod(lambda cls, sec: FakeSP())
    try:
        at = AppTest.from_file(str(ROOT / "pages" / "1_Portfolio_dashboard.py"), default_timeout=120)
        at.session_state["role"] = "approver"
        at.session_state["user"] = "Test user"
        at.secrets["sharepoint"] = {"tenant_id": "x"}
        at.run()
    finally:
        sp_mod.SharePointClient.from_secrets = orig
    assert not at.exception, at.exception
    assert at.metric[0].value == "60"


def test_dashboard_blocks_writers():
    at = AppTest.from_file(str(ROOT / "pages" / "1_Portfolio_dashboard.py"), default_timeout=60)
    at.session_state["role"] = "writer"
    at.run()
    assert not at.exception and not at.metric
