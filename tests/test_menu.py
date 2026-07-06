# tests/test_menu.py
from subtap.ui.menu import Menu


class TestMenu:
    def test_initial_state(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        assert m.cursor == 0
        assert m.top_index == 0

    def test_move_down(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        m.move_down()
        assert m.cursor == 1

    def test_move_up_clamp(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        m.move_up()
        assert m.cursor == 0

    def test_move_down_clamp(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        m.cursor = 2
        m.move_down()
        assert m.cursor == 2

    def test_jump_to_top(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        m.cursor = 2
        m.jump_top()
        assert m.cursor == 0

    def test_jump_to_bottom(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        m.jump_bottom()
        assert m.cursor == 2

    def test_selected_index(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        assert m.selected_index() == "A"
        m.move_down()
        assert m.selected_index() == "B"

    def test_render_current_item_highlighted(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        lines = m.render()
        assert "➤" in lines[2]  # 第三行是第一个菜单项
        assert "A" in lines[2]

    def test_render_non_current_item_no_arrow(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        lines = m.render()
        assert "➤" not in lines[3]

    def test_render_title(self):
        m = Menu(title="Subtap", items=["A", "B"])
        lines = m.render()
        assert "Subtap" in lines[0]

    def test_render_footer(self):
        m = Menu(title="测试", items=["A", "B"])
        lines = m.render()
        assert "Enter" in lines[-1]

    def test_items_per_page_clamp(self):
        m = Menu(title="测试", items=["A"] * 100, max_items=10)
        assert m.items_per_page == 10

    def test_scroll_when_cursor_exceeds_page(self):
        items = [f"item{i}" for i in range(20)]
        m = Menu(title="测试", items=items, max_items=5)
        for _ in range(6):
            m.move_down()
        assert m.top_index > 0
