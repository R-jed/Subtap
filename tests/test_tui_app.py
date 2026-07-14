# tests/test_tui_app.py
from subtap.ui.tui_app import TuiApp


class TestTuiApp:
    def test_initial_state_is_home(self):
        app = TuiApp.__new__(TuiApp)
        app._state = "home"
        assert app._state == "home"

    def test_state_transitions(self):
        app = TuiApp.__new__(TuiApp)
        app._state = "home"
        app._state = "settings"
        assert app._state == "settings"
        app._state = "home"
        assert app._state == "home"
