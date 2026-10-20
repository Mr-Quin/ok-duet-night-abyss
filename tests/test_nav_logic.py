# 导航层的纯逻辑测试：用假后端记录导航器做出的动作，不需要截图和 OCR
import unittest

import numpy as np

from src.nav import (BookSection, CommissionTab, Letter, MainMenu, Mission, Nav, NavError, Nightbook, NoSuchEntry,
                     NotOffered, Page, World, WrongMission)
from src.nav import screens as S
from src.nav import text_zh as T
from src.nav.backend import Backend, Screen
from src.nav.edges import open_nightbook_row, same_name
from src.nav import handlers as H
from src.nav.navigator import Navigator

BLANK = np.zeros((90, 160, 3), np.uint8)


def screen(*texts):
    """texts 为 (文字, x, y)。"""
    return Screen(BLANK, [{'t': t, 'x': x, 'y': y} for t, x, y in texts])


class FakeBackend(Backend):
    def __init__(self):
        self.actions = []

    def frame(self):
        return BLANK

    def ocr(self, img):
        return []

    def click(self, x, y):
        self.actions.append(('click', round(x, 3), round(y, 3)))

    def key(self, name):
        self.actions.append(('key', name))

    def scroll(self, x, y, notches):
        self.actions.append(('scroll', notches))

    def drag(self, x0, y0, x1, y1):
        self.actions.append(('drag', round(x0, 3), round(x1, 3)))

    def park(self):
        self.actions.append(('park',))

    def sleep(self, seconds):
        pass


def navigator(target, **kwargs):
    backend = FakeBackend()
    return Navigator(backend, target, log=lambda msg: None, atlas={}, **kwargs), backend


class TestNames(unittest.TestCase):

    def test_one_misread_character_is_the_same_row(self):
        self.assertTrue(same_name('枯萎游击秽兽', '枯菱游击秽兽'))
        self.assertTrue(same_name('复仇飘浮秽兽II', '复仇飘浮秽兽Ⅱ'))

    def test_numerals_and_different_names_differ(self):
        self.assertFalse(same_name('复仇飘浮秽兽II', '复仇飘浮秽兽III'))
        self.assertFalse(same_name('守护野蜂暗箭', '守护野蜂利刃'))


class TestLevelPositions(unittest.TestCase):

    def test_misread_label_is_ignored(self):
        # 55 被读成 50，落在拟合直线外
        scr = screen(('20', 0.075, 0.252), ('40', 0.075, 0.398), ('50', 0.075, 0.568), ('65', 0.075, 0.69))
        levels = S.level_positions(scr)
        self.assertAlmostEqual(levels[65], 0.69, delta=0.01)
        self.assertAlmostEqual(levels[50], 0.252 + 3 * S.LEVEL_STEP, delta=0.01)

    def test_one_label_is_not_enough(self):
        self.assertEqual(S.level_positions(screen(('30', 0.075, 0.3))), {})


class SwallowingBackend(FakeBackend):
    """主菜单上前几次按 esc 被游戏吞掉，之后才回到大世界。"""

    def __init__(self, swallowed):
        super().__init__()
        self.swallowed = swallowed

    def read(self):
        if self.actions.count(('key', 'esc')) <= self.swallowed:
            return screen((T.UID, 0.1, 0.1), (T.SHOP, 0.2, 0.3))
        return screen((T.LV, 0.05, 0.95))


class TestStuck(unittest.TestCase):

    def test_last_allowed_retry_is_checked_before_giving_up(self):
        backend = SwallowingBackend(swallowed=3)
        nav = Navigator(backend, World(), log=lambda msg: None, atlas={})
        self.assertTrue(nav.run())
        self.assertEqual(backend.actions.count(('key', 'esc')), 4)

    def test_input_that_never_works_is_reported(self):
        nav = Navigator(SwallowingBackend(swallowed=99), World(), log=lambda msg: None, atlas={})
        with self.assertRaisesRegex(NavError, '一直在重复'):
            nav.run()


class SliderBackend(FakeBackend):
    """开始界面的自动轮次面板。点滑条落在点的位置再差 miss 轮（track=False 时点了没反应），按钮每次一轮。"""

    def __init__(self, rounds, miss=0, track=True):
        super().__init__()
        self.rounds, self.miss, self.track = rounds, miss, track

    def read(self):
        return screen((T.START[0], 0.85, 0.9), (T.AUTO_LABEL, 0.62, 0.6), ('轮次 %d/99' % self.rounds, 0.78, 0.643))

    def click(self, x, y):
        super().click(x, y)
        if x in (S.AUTO_MIN_X, S.AUTO_MAX_X):
            self.rounds = 1 if x == S.AUTO_MIN_X else 99
        elif x in (S.AUTO_PLUS_X, S.AUTO_MINUS_X):
            self.rounds += 1 if x == S.AUTO_PLUS_X else -1
        elif self.track:
            self.rounds = round((x - S.AUTO_SLIDER_X) / S.AUTO_SLIDER_STEP) + 1 + self.miss


class TestAutoRounds(unittest.TestCase):

    def test_far_target_is_tapped_on_the_track_then_corrected_with_buttons(self):
        backend = SliderBackend(1, miss=-2)
        Nav(backend).set_auto_rounds(39)
        self.assertEqual(backend.rounds, 39)
        self.assertEqual(backend.actions[0], ('click', round(S.auto_slider_x(39), 3), 0.682))
        self.assertEqual(backend.actions.count(('click', S.AUTO_PLUS_X, 0.682)), 2)
        self.assertFalse(any(a[0] == 'drag' for a in backend.actions))

    def test_a_track_that_ignores_the_tap_falls_back_to_the_nearer_end(self):
        backend = SliderBackend(1, track=False)
        Nav(backend).set_auto_rounds(85)
        self.assertEqual(backend.rounds, 85)
        self.assertIn(('click', S.AUTO_MAX_X, 0.682), backend.actions)
        self.assertEqual(backend.actions.count(('click', S.AUTO_MINUS_X, 0.682)), 14)

    def test_near_target_uses_the_buttons_only(self):
        backend = SliderBackend(39)
        Nav(backend).set_auto_rounds(41)
        self.assertEqual(backend.rounds, 41)
        self.assertFalse(any(a[0] == 'drag' for a in backend.actions))

class TestStartingTheGame(unittest.TestCase):
    VERSION = ('OS_ Windows_ Product_1.6.208.1', 0.11, 0.99)

    def classify(self, *texts):
        return S.classify(screen(*texts), {})

    def test_title_screen_is_entered_by_clicking(self):
        found, info = self.classify(('当前区服', 0.92, 0.04), ('点击进入游戏', 0.5, 0.9), self.VERSION)
        self.assertEqual(found, 'title')
        nav, backend = navigator(World())
        H.on_title(nav, screen(), info)
        self.assertEqual(backend.actions, [('click', 0.5, 0.9)])

    def test_boot_screens_are_waited_through_without_pressing_anything(self):
        for texts in ([('光敏性癫痫警告', 0.5, 0.3)], [('检查更新中·', 0.5, 0.9), self.VERSION],
                      [('登录', 0.5, 0.9), self.VERSION]):
            found, info = self.classify(*texts)
            self.assertEqual(found, 'boot', texts)
            nav, backend = navigator(World())
            self.assertIsNone(H.on_boot(nav, screen(), info))
            self.assertEqual(backend.actions, [])

    def test_a_blank_frame_while_starting_is_waited_on(self):
        nav, backend = navigator(World())
        H.on_boot(nav, screen(), {'login': False})
        self.assertIsNone(H.on_unknown(nav, screen(), {}))
        self.assertEqual(backend.actions, [])

    def test_waiting_too_long_at_login_asks_for_a_manual_login(self):
        nav, backend = navigator(World())
        with self.assertRaisesRegex(NavError, '手动登录'):
            for _ in range(H.MAX_LOGIN_WAITS + 1):
                H.on_boot(nav, screen(), {'login': True})

    def test_a_dialog_while_starting_is_left_to_the_user(self):
        found, info = self.classify(('发现新版本，是否下载？', 0.5, 0.45), ('确定', 0.6, 0.6), ('取消', 0.4, 0.6),
                                    ('点击进入游戏', 0.5, 0.9), self.VERSION)
        self.assertEqual(found, 'boot_dialog')
        nav, backend = navigator(World())
        with self.assertRaisesRegex(NavError, '发现新版本'):
            H.on_boot_dialog(nav, screen(), info)
        self.assertEqual(backend.actions, [])


class TestRoutes(unittest.TestCase):

    def test_nightbook_route(self):
        self.assertEqual(Nightbook(65, 2).route(),
                         [('world', None), ('commission', T.TABS[1]), ('start', T.TABS[1])])

    def test_page_goes_through_its_book_section(self):
        self.assertEqual(Page('boss_map').route(),
                         [('world', None), ('book', '梦魔残声'), ('page', 'boss_map')])

    def test_book_section_with_commissions_is_the_commission_page(self):
        self.assertEqual(BookSection(T.SECTIONS[1]).route(), [('world', None), ('commission', None)])


class TestRouteWalking(unittest.TestCase):

    def test_world_opens_the_book_or_the_main_menu(self):
        nav, backend = navigator(CommissionTab(T.TABS[0]))
        nav.follow_route(screen(), 'world', {})
        nav2, backend2 = navigator(MainMenu())
        nav2.follow_route(screen(), 'world', {})
        self.assertEqual(backend.actions, [('key', 'l')])
        self.assertEqual(backend2.actions, [('key', 'esc')])

    def test_book_section_switches_to_the_commission_page(self):
        nav, backend = navigator(CommissionTab(T.TABS[1]))
        nav.follow_route(screen(), 'book', {'section': '今日行程'})
        self.assertEqual(backend.actions, [('click', S.SECTION_X[1], S.SECTION_Y)])

    def test_commission_tab_switch(self):
        nav, backend = navigator(CommissionTab(T.TABS[2]))
        nav.follow_route(screen(), 'commission', {'tab': T.TABS[0]})
        self.assertEqual(backend.actions, [('click', S.TAB_X[2], S.TAB_Y)])

    def test_unrelated_screen_backs_out(self):
        nav, backend = navigator(CommissionTab(T.TABS[0]))
        nav.follow_route(screen(), 'menu', {'name': '背包'})
        self.assertEqual(backend.actions, [('key', 'esc')])

    def test_arrived(self):
        nav, backend = navigator(CommissionTab(T.TABS[3]))
        self.assertTrue(nav.follow_route(screen(), 'commission', {'tab': T.TABS[3]}))
        self.assertEqual(backend.actions, [])

    def test_unreadable_tab_parks_the_cursor_before_clicking(self):
        nav, backend = navigator(CommissionTab(T.TABS[2]))
        self.assertIsNone(H.on_commission(nav, screen(), {'tab': None}))
        self.assertIsNone(H.on_commission(nav, screen(), {'tab': None}))
        self.assertIn(('park',), backend.actions)


class TestStartScreen(unittest.TestCase):

    def test_other_tier_on_offer(self):
        info = {'via': T.TABS[0], 'mode': '扼守/无尽', 'lv': 50,
                'tiers': [{'lv': 50, 'y': 0.3}, {'lv': 60, 'y': 0.35}]}
        self.assertIsNone(H.start_matches(info, Mission('扼守/无尽', lv=60).goal()))
        self.assertFalse(H.start_matches(info, Mission('驱离', lv=60).goal()))

    def test_entry_opening_another_mission_is_reported(self):
        nav, backend = navigator(Nightbook(20, 0, mode='扼守/无尽', lv=20))
        nav.state['entered_row'] = '爆破疾冲秽兽'
        info = {'via': T.TABS[1], 'mode': '驱离', 'lv': 10, 'tiers': [{'lv': 10, 'y': 0.22}],
                'entries': [], 'column': None}
        with self.assertRaises(WrongMission):
            H.on_start(nav, screen(), info)


    def test_letter_goal_backs_out_of_another_start_screen(self):
        nav, backend = navigator(Letter('驱逐'))
        info = {'via': T.TABS[0], 'mode': '扼守/无尽', 'lv': 60, 'tiers': [{'lv': 60, 'y': 0.3}],
                'entries': [], 'column': None}
        self.assertFalse(H.on_start(nav, screen(), info))
        self.assertEqual(backend.actions, [('key', 'esc')])

    def test_a_letter_column_without_the_mission_this_hour_is_reported(self):
        nav, _ = navigator(Letter(T.ENDLESS, column='武器'))
        info = {'via': T.TABS[2], 'mode': '追缉', 'lv': 40, 'tiers': [], 'column': '武器',
                'entries': [{'mode': '追缉', 'y': 0.22}, {'mode': '调停', 'y': 0.28}, {'mode': '避险', 'y': 0.33}]}
        with self.assertRaises(NotOffered) as raised:
            H.on_start(nav, screen(), info)
        self.assertEqual(raised.exception.offered, ['追缉', '调停', '避险'])

    def test_the_letter_picker_is_not_the_manual_popup(self):
        before = screen((T.LETTER_TITLE, 0.47, 0.33), (T.MANUAL_SKIP, 0.47, 0.48), ('Space', 0.77, 0.64),
                        (T.LETTER_GIVE_UP, 0.61, 0.64))
        between = screen((T.LETTER_TITLE, 0.47, 0.33), (T.MANUAL_SKIP, 0.47, 0.48), ('Space', 0.55, 0.64))
        self.assertEqual(S.classify(before, {}), ('letter_popup', {'before_run': True}))
        self.assertEqual(S.classify(between, {}), ('letter_popup', {'before_run': False}))


class TestNightbookRows(unittest.TestCase):
    ROWS = ['残火暴徒秽兽', '霹雳疾冲秽兽', '枯萎游击秽兽', '凛霜疾冲秽兽']

    def page(self, names):
        texts = []
        for k, name in enumerate(names):
            y = 0.25 + 0.1 * k
            texts += [(name, 0.2, y), (T.GO, 0.62, y)]
        return screen(*texts)

    def nightbook(self, row):
        nav, backend = navigator(Nightbook(30, row))
        nav.cache = {'names/30': list(self.ROWS)}
        levels = {lv: 0.25 + 0.07 * k for k, lv in enumerate(S.LEVELS)}
        return nav, backend, {'tab': T.TABS[1], 'levels': levels}

    def test_selects_the_level_then_presses_the_row(self):
        nav, backend, info = self.nightbook(2)
        scr = self.page(self.ROWS)
        open_nightbook_row(nav, scr, None, None, dict(info))
        open_nightbook_row(nav, scr, None, None, dict(info))
        self.assertEqual(backend.actions, [('click', S.LEVEL_X, round(info['levels'][30], 3)), ('click', 0.62, 0.45)])
        self.assertEqual(nav.state['entered_row'], '枯萎游击秽兽')

    def test_misread_name_does_not_add_a_row(self):
        nav, backend, info = self.nightbook(4)
        scr = self.page(['残火暴徒秽兽', '霹雳疾冲秽兽', '枯菱游击秽兽', '凛霜疾冲秽兽'])
        with self.assertRaises(NoSuchEntry) as raised:
            for _ in range(4):
                open_nightbook_row(nav, scr, None, None, dict(info))
        self.assertEqual(len(raised.exception.names), 4)

    def test_rows_are_counted_by_position_across_a_scroll(self):
        rows = ['爆破疾冲秽兽', '猩红游击秽兽', '守护飘浮秽兽Ⅱ', '凛霜灼心秽兽', '复仇蒙恩的先锋', '霜狱蒙恩的执事']
        nav, backend = navigator(Nightbook(20, 5))
        nav.cache = {'names/20': rows[:5]}
        levels = {lv: 0.25 + 0.07 * k for k, lv in enumerate(S.LEVELS)}
        info = {'tab': T.TABS[1], 'levels': levels}
        nav.state['nightbook'] = {'level': 20, 'names': None, 'seen': []}
        # 滚动后「Ⅱ」读成了「ⅡI」，按名字去重会多出一行，按位置对齐不会
        first = self.page(rows[:5])
        second = self.page(['猩红游击秽兽', '守护飘浮秽兽ⅡI', '凛霜灼心秽兽', '复仇蒙恩的先锋', '霜狱蒙恩的执事'])
        for scr in (first, second):
            open_nightbook_row(nav, scr, None, None, dict(info))
        self.assertEqual(nav.state['entered_row'], '霜狱蒙恩的执事')
        self.assertEqual(nav.cache['names/20'][-1], '霜狱蒙恩的执事')
        self.assertEqual(len(nav.cache['names/20']), 6)

    def test_the_level_column_read_once_is_remembered_on_the_page(self):
        nav, backend, info = self.nightbook(5)
        rows = ['残火暴徒秽兽', '霹雳疾冲秽兽', '枯萎游击秽兽', '凛霜疾冲秽兽', '复仇蒙恩的先锋', '霜狱蒙恩的执事']
        nav.cache = {'names/30': rows[:4]}
        open_nightbook_row(nav, self.page(rows[:4]), None, None, dict(info))
        open_nightbook_row(nav, self.page(rows[:4]), None, None, dict(info))
        # 滚动后等级栏读不出来（FakeBackend 的 OCR 什么都读不到），还按记下的位置走
        open_nightbook_row(nav, self.page(rows[1:]), None, None, {'tab': T.TABS[1]})
        self.assertEqual(nav.state['entered_row'], '霜狱蒙恩的执事')

    def test_a_half_hidden_row_keeps_its_place_without_a_name(self):
        # 只露出一半的行，名字的位置上读到的是列表顶上的花纹
        scr = self.page(['HTHHHIHRYH', '残火暴徒秽兽', '霹雳疾冲秽兽'])
        self.assertEqual([r['name'] for r in S.nightbook_rows(scr)], [None, '残火暴徒秽兽', '霹雳疾冲秽兽'])

    def test_a_row_whose_name_is_unreadable_still_aligns(self):
        from src.nav.edges import align
        known = ['爆破疾冲秽兽', '猩红游击秽兽', '守护飘浮秽兽Ⅱ', '凛霜灼心秽兽', '复仇蒙恩的先锋']
        self.assertEqual(align(known, [None, '守护飘浮秽兽ⅡI', '凛霜灼心秽兽', '复仇蒙恩的先锋', None]), 1)
        self.assertIsNone(align(known, [None, None, '霜狱蒙恩的执事']))
        # 只露出一半的边上那行读成了别的字
        self.assertEqual(align(known, ['相以', '凛霜灼心秽兽', '复仇蒙恩的先锋', '霜狱蒙恩的执事']), 2)
        self.assertIsNone(align(known, ['猩红游击秽兽', '相以', '凛霜灼心秽兽']))


class TestLeavingARun(unittest.TestCase):

    def test_unstarted_run_is_given_up(self):
        nav, backend = navigator(World())
        H.on_dungeon(nav, screen(), {'to_objective': True, 'round': 1})
        self.assertEqual(backend.actions, [('key', 'esc')])
        self.assertTrue(nav.state['giving_up'])

    def test_run_in_progress_is_waited_out(self):
        nav, backend = navigator(World())
        self.assertIsNone(H.on_dungeon(nav, screen(), {'to_objective': False, 'round': 2}))
        self.assertEqual(backend.actions, [])

    def test_a_run_without_rounds_checks_the_menu_once_then_waits(self):
        nav, backend = navigator(World())
        info = {'to_objective': False, 'round': None, 'mode': '驱逐'}
        self.assertFalse(H.on_dungeon(nav, screen(), info))
        self.assertEqual(backend.actions, [('key', 'esc')])
        self.assertTrue(nav.state['giving_up'])
        self.assertIsNone(H.on_dungeon(nav, screen(), info))
        self.assertEqual(backend.actions, [('key', 'esc')])

    def test_the_auto_rounds_switch_is_found_from_the_count_when_the_label_is_unreadable(self):
        info = S.auto_round_info(screen(('轮次99/99', 0.784, 0.644)))
        self.assertTrue(info['auto_on'])
        self.assertAlmostEqual(info['auto_switch'][1], 0.644 - S.AUTO_ROW_DY)

    def test_a_run_without_rounds_is_recognised_by_its_mode_title(self):
        screen_name, info = S.detect_dungeon(screen(('驱逐', 0.033, 0.274), ('驱逐敌人', 0.07, 0.31)), None)
        self.assertEqual((screen_name, info['mode']), ('dungeon', '驱逐'))

    def test_gives_up_only_when_nothing_is_earned(self):
        menu = {'resume': {'x': 0.5, 'y': 0.9}, 'give_up': {'x': 0.9, 'y': 0.9}}
        nav, backend = navigator(World())
        nav.state['giving_up'] = True
        H.on_dungeon_menu(nav, screen(), dict(menu, nothing_earned=True))
        nav2, backend2 = navigator(World())
        nav2.state['giving_up'] = True
        H.on_dungeon_menu(nav2, screen(), dict(menu, nothing_earned=False))
        self.assertEqual(backend.actions, [('click', 0.9, 0.9)])
        self.assertEqual(backend2.actions, [('click', 0.5, 0.9)])
        self.assertFalse(nav2.state['giving_up'])

    def test_exit_is_confirmed_only_after_the_menu_showed_no_reward(self):
        confirm = {'cancel': {'x': 0.4, 'y': 0.6}, 'confirm': {'x': 0.6, 'y': 0.6}}
        clicks = []
        for state in ({}, {'giving_up': True}, {'giving_up': True, 'no_reward_seen': True}):
            nav, backend = navigator(World())
            nav.state.update(state)
            H.on_exit_confirm(nav, screen(), confirm)
            clicks.append(backend.actions)
        self.assertEqual(clicks, [[('click', 0.4, 0.6)], [('click', 0.4, 0.6)], [('click', 0.6, 0.6)]])

    def test_round_dialog_retreats(self):
        nav, backend = navigator(World())
        H.on_round_dialog(nav, screen(), {'auto': (1, 3), 'retreat': {'x': 0.33, 'y': 0.69}})
        self.assertEqual(backend.actions, [('click', 0.33, 0.69)])

    def test_manual_popup_before_a_run_is_closed(self):
        nav, backend = navigator(World())
        H.on_manual_popup(nav, screen(), {'before_run': True})
        self.assertEqual(backend.actions, [('key', 'esc')])


if __name__ == '__main__':
    unittest.main()
