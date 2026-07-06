import time
from subtap.ui.spinner import Spinner


class TestSpinner:
    def test_start_and_stop(self):
        s = Spinner()
        s.start("加载中")
        time.sleep(0.15)
        s.stop()
        assert not s._thread.is_alive()

    def test_stop_without_start(self):
        s = Spinner()
        s.stop()  # 不应报错
