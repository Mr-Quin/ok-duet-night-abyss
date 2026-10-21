# 导航层界面判据测试：真实截图 + 真实 OCR，走 ok-script 后端
import unittest

from ok.test.TaskTestCase import TaskTestCase

from src.config import config
from src.nav import screens as S
from src.nav import text_zh as T
from src.nav.okscript import OkScriptBackend
from src.run import exploration as X
from src.run import observe as O
from src.tasks.AutoDefence import AutoDefence
from src.tasks.fullauto.marker_walk import MarkerWalk

NAV = 'tests/images/nav/'
IMAGES = 'tests/images/'
LETTER = 'tests/images/letter/'


class TestNavScreens(TaskTestCase):
    task_class = AutoDefence

    config = config

    def read(self, path):
        self.set_image(path)
        backend = OkScriptBackend(self.task)
        scr = backend.read()
        return scr, S.classify(scr, S.load_atlas())

    def assertScreen(self, path, screen, **expected):
        _, (found, info) = self.read(path)
        self.assertEqual(found, screen, path)
        for key, value in expected.items():
            self.assertEqual(info.get(key), value, '%s: %s' % (path, key))
        return info

    # ---- 局外菜单 ----

    def test_world(self):
        self.assertScreen(NAV + 'world.png', 'world')

    def test_main_menu(self):
        self.assertScreen(NAV + 'main_menu.png', 'main_menu')

    def test_book_section(self):
        self.assertScreen(NAV + 'book_boss.png', 'book', section='梦魔残声')

    def test_commission_tabs(self):
        self.assertScreen(NAV + 'commission_tasks.png', 'commission', tab=T.TABS[0])
        self.assertScreen(NAV + 'commission_letters.png', 'commission', tab=T.TABS[2])
        self.assertScreen(NAV + 'commission_bounty.png', 'commission', tab=T.TABS[3])

    def test_menu_and_page_from_atlas(self):
        self.assertScreen(NAV + 'menu_map.png', 'menu', name='地图')
        self.assertScreen(NAV + 'page_maze.png', 'page', name='迷津')

    # ---- 夜航手册 ----

    def test_nightbook_selected_level(self):
        for level in (30, 65):
            scr, (screen, info) = self.read(NAV + 'nightbook_lv%d_top.png' % level)
            self.assertEqual((screen, info['tab']), ('commission', T.TABS[1]))
            self.assertEqual(S.selected_level(scr, info['levels']), level)

    def test_a_level_at_the_bottom_edge_is_not_taken_for_the_selected_one(self):
        # below the panel is the bright sand background
        scr, _ = self.read(NAV + 'nightbook_lv60_panel_edge.png')
        levels = {20: 0.25, 30: 0.33, 40: 0.40, 50: 0.47, 55: 0.54, 60: 0.62, 65: 0.69, 70: 0.76, 75: 0.80}
        self.assertEqual(S.selected_level(scr, levels), 60)
        self.assertEqual(S.selected_level(scr, {**levels, 80: 0.86}), 60)

    def test_nightbook_rows(self):
        scr, _ = self.read(NAV + 'nightbook_lv65_top.png')
        self.assertEqual([r['name'] for r in S.nightbook_rows(scr)][:2], ['霜狱野蜂暗箭', '浴血野蜂利刃'])
        scr, _ = self.read(NAV + 'nightbook_lv65_bottom.png')
        self.assertEqual(S.nightbook_rows(scr)[-1]['name'], '掠影野蜂利刃')

    # ---- 开始界面 ----

    def test_start_from_nightbook_with_auto_rounds(self):
        self.assertScreen(NAV + 'start_nightbook_lv30.png', 'start', via=T.TABS[1], mode='扼守/无尽', lv=30,
                          auto_on=True, auto_rounds=1)

    def test_start_from_commissions_with_tiers(self):
        info = self.assertScreen(NAV + 'start_mission_lv60.png', 'start', via=T.TABS[0], mode='扼守/无尽', lv=60,
                                 auto_on=False)
        self.assertEqual([t['lv'] for t in info['tiers']], [40, 50, 60, 70, 80])

    def test_start_from_letters(self):
        info = self.assertScreen(NAV + 'start_letter.png', 'start', via=T.TABS[2], mode='驱逐')
        self.assertIn('驱逐', [e['mode'] for e in info['entries']])

    def test_project_start_screen(self):
        self.assertScreen(IMAGES + 'start_screen_defence.png', 'start')

    # ---- 局内 ----

    def test_run_before_the_first_wave(self):
        self.assertScreen(NAV + 'dungeon_to_objective.png', 'dungeon', to_objective=True)

    def test_in_run_menu_with_nothing_earned(self):
        self.assertScreen(NAV + 'dungeon_menu_nothing_earned.png', 'dungeon_menu', nothing_earned=True)

    def test_exit_confirmation(self):
        self.assertScreen(NAV + 'exit_confirm.png', 'exit_confirm')

    def test_round_dialog_auto_rounds(self):
        self.assertScreen(NAV + 'round_dialog_auto.png', 'round_dialog', auto=(1, 1))
        self.assertScreen(NAV + 'round_dialog_auto_done.png', 'round_dialog', auto=None)

    def test_manual_popups(self):
        self.assertScreen(IMAGES + 'manual_select_from_start.png', 'manual_popup', before_run=True)
        self.assertScreen(IMAGES + 'manual_select_next_round.png', 'manual_popup', before_run=False)

    def test_reward_popup(self):
        self.assertScreen(NAV + 'reward_popup.png', 'blank_close')

    def test_event_splash_after_login(self):
        self.assertScreen(NAV + 'event_splash.png', 'splash')

    def test_result(self):
        self.assertScreen(IMAGES + 'result_defence.png', 'result')

    # ---- 走位与轮次 ----

    def test_marker_and_distance(self):
        self.set_image(NAV + 'dungeon_to_objective.png')
        seen = MarkerWalk(self.task).find(self.task.frame)
        self.assertIsNotNone(seen)
        x, metres = seen
        self.assertLess(abs(x), 0.1)
        self.assertEqual(metres, 29)

    def test_result_screen_is_not_the_between_round_popup(self):
        self.set_image(IMAGES + 'result_defence.png')
        self.assertEqual(O.observe(self.task), O.RESULT)
        self.set_image(IMAGES + 'manual_select_next_round.png')
        self.assertEqual(O.observe(self.task), O.MANUAL)


    # ---- 技能 ----

    def test_a_toggle_ultimate_that_is_on_reads_no_cost(self):
        self.set_image(IMAGES + 'ult_toggle_on.png')
        self.assertFalse(self.task.ultimate_cost())
        self.set_image(IMAGES + 'ult_toggle_off.png')
        self.assertEqual(self.task.ultimate_cost(), 8)

    # ---- 委托密函 ----

    def test_letter_tab_lists_the_endless_missions(self):
        scr, (screen, info) = self.read(LETTER + 'letter_tab.png')
        self.assertEqual((screen, info['tab']), ('commission', T.TABS[2]))
        self.assertEqual(sorted(i['t'] for i in scr.items if T.ENDLESS in i['t']), ['扼守/无尽', '探险/无尽'])

    def test_letter_start_screen(self):
        self.assertScreen(LETTER + 'letter_start.png', 'start', via=T.TABS[2], mode='探险/无尽', column='角色',
                          auto_on=True)

    def test_letter_picker_before_the_run(self):
        self.assertScreen(LETTER + 'letter_popup.png', 'letter_popup', before_run=True)

    def test_exploration_device_prompts(self):
        explore = X.Exploration(self.task)
        for image, region, text in (('explore_prompt.png', X.PROMPT_BOX, X.PROMPT),
                                    ('explore_quick_solve.png', X.QUICK_SOLVE_BOX, X.QUICK_SOLVE),
                                    ('explore_solved.png', X.SOLVED_BOX, X.SOLVED)):
            with self.subTest(image=image):
                self.set_image(LETTER + image)
                self.assertTrue(explore.shows(region, text))
        self.set_image(LETTER + 'explore_solved.png')
        self.assertFalse(explore.shows(X.QUICK_SOLVE_BOX, X.QUICK_SOLVE))

if __name__ == '__main__':
    unittest.main()
