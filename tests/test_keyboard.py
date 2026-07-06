# tests/test_keyboard.py
from unittest.mock import patch
from subtap.ui.keyboard import Key, KeyReader


class TestKeyConstants:
    def test_key_constants_exist(self):
        assert Key.UP == "UP"
        assert Key.DOWN == "DOWN"
        assert Key.ENTER == "ENTER"
        assert Key.QUIT == "QUIT"
        assert Key.TOP == "TOP"
        assert Key.BOTTOM == "BOTTOM"


class TestCSISequenceParsing:
    def _make_reader(self):
        reader = KeyReader.__new__(KeyReader)
        reader._fd = 0
        reader.force_char_mode = False
        return reader

    def test_csi_up(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"[", b"A"]):
            assert reader._parse_csi_ss3() == Key.UP

    def test_csi_down(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"[", b"B"]):
            assert reader._parse_csi_ss3() == Key.DOWN

    def test_csi_right(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"[", b"C"]):
            assert reader._parse_csi_ss3() == Key.RIGHT

    def test_csi_left(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"[", b"D"]):
            assert reader._parse_csi_ss3() == Key.LEFT

    def test_csi_delete(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"[", b"3", b"~"]):
            assert reader._parse_csi_ss3() == Key.DELETE

    def test_ss3_up(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"O", b"A"]):
            assert reader._parse_csi_ss3() == Key.UP

    def test_ss3_down(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"O", b"B"]):
            assert reader._parse_csi_ss3() == Key.DOWN


class TestNormalModeKeys:
    def _make_reader(self):
        reader = KeyReader.__new__(KeyReader)
        reader._fd = 0
        reader.force_char_mode = False
        return reader

    def test_j_is_down(self):
        reader = self._make_reader()
        assert reader._map_normal(b"j") == Key.DOWN

    def test_k_is_up(self):
        reader = self._make_reader()
        assert reader._map_normal(b"k") == Key.UP

    def test_h_is_left(self):
        reader = self._make_reader()
        assert reader._map_normal(b"h") == Key.LEFT

    def test_l_is_right(self):
        reader = self._make_reader()
        assert reader._map_normal(b"l") == Key.RIGHT

    def test_q_is_quit(self):
        reader = self._make_reader()
        assert reader._map_normal(b"q") == Key.QUIT

    def test_enter(self):
        reader = self._make_reader()
        assert reader._map_normal(b"\r") == Key.ENTER

    def test_space(self):
        reader = self._make_reader()
        assert reader._map_normal(b" ") == Key.SPACE

    def test_ctrl_c_is_quit(self):
        reader = self._make_reader()
        assert reader._map_normal(b"\x03") == Key.QUIT

    def test_backspace(self):
        reader = self._make_reader()
        assert reader._map_normal(b"\x7f") == Key.DELETE

    def test_printable_char(self):
        reader = self._make_reader()
        assert reader._map_normal(b"a") == "CHAR:a"

    def test_digit_char(self):
        reader = self._make_reader()
        assert reader._map_normal(b"3") == "CHAR:3"


class TestForceCharMode:
    def _make_reader(self):
        reader = KeyReader.__new__(KeyReader)
        reader._fd = 0
        reader.force_char_mode = True
        return reader

    def test_printable_is_char(self):
        reader = self._make_reader()
        assert reader._map_force_char(b"a") == "CHAR:a"

    def test_space_is_space(self):
        reader = self._make_reader()
        assert reader._map_force_char(b" ") == Key.SPACE

    def test_enter_is_enter(self):
        reader = self._make_reader()
        assert reader._map_force_char(b"\r") == Key.ENTER

    def test_ctrl_u_is_clear(self):
        reader = self._make_reader()
        assert reader._map_force_char(b"\x15") == Key.CLEAR_LINE
