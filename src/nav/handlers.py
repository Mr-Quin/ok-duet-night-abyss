"""无论在路线的哪一步出现都要单独处理的界面：局内、开始界面、委托页的过渡状态。

局内的规则保证路上遇到正在进行的一局时，在第一个不损失奖励的时机离开：轮次弹窗撤离、
结算界面退出，或者在本局还没有任何奖励时放弃。

用到的 nav.state 键：giving_up（正在放弃本局）、no_reward_seen（局内菜单上看到了「无奖励」，只有这时才能确认放弃）、loading（刚离开副本或正在启动游戏，在等加载）、
run_waits（局内等了几次）、login_waits（启动时在登录这一步等了几次）、
entered_row（从夜航手册哪一行进的开始界面，edges.py 写入）。
"""
from src.nav import graph
from src.nav import text_zh as T
from src.nav.graph import NavError, WrongMission

# 局内一直等不到弹窗或结算时，最多等这么多次（每次约 0.4 秒加一次识别）
MAX_RUN_WAITS = 400
# 启动时停在登录这一步超过这么多次，多半是要手动输入账号
MAX_LOGIN_WAITS = 150
# 开始界面左侧条目的点击位置
TIER_X = 0.08
LETTER_ENTRY_X = 0.05


def start_matches(info, goal):
    """开始界面是否就是目标。等级不对但界面上有目标等级可选时返回 None。"""
    if goal['via'] and info['via'] and goal['via'] != info['via']:
        return False
    if goal['mode'] and not (info['mode'] and goal['mode'] in info['mode']):
        return False
    if goal['lv'] and info['lv'] != goal['lv']:
        return None if any(t['lv'] == goal['lv'] for t in info['tiers']) else False
    return True


def wait_in_run(nav):
    nav.state['run_waits'] = nav.state.get('run_waits', 0) + 1
    if nav.state['run_waits'] < MAX_RUN_WAITS:
        return None
    raise NavError('局内等了很久也没有出现轮次弹窗或结算，不会自动放弃这一局')


@graph.handler('round_dialog')
def on_round_dialog(nav, scr, info):
    nav.log('  撤离，轮次 %s' % (info['auto'],))
    nav.click(info['retreat'][0])
    return False


@graph.handler('result')
def on_result(nav, scr, info):
    nav.log('  退出结算界面')
    nav.state['loading'] = True
    nav.b.key('esc')
    return False


@graph.handler('exit_confirm')
def on_exit_confirm(nav, scr, info):
    if nav.state.get('giving_up') and nav.state.get('no_reward_seen') and info['confirm']:
        nav.log('  确认结束：本局还没有奖励')
        nav.click(info['confirm'])
        nav.state.update(giving_up=False, no_reward_seen=False, loading=True)
        return False
    nav.log('  取消结束任务的确认')
    if info['cancel']:
        nav.click(info['cancel'])
    else:
        nav.b.key('esc')
    return False


@graph.handler('dungeon_menu')
def on_dungeon_menu(nav, scr, info):
    if nav.state.get('giving_up') and info['nothing_earned']:
        nav.log('  放弃挑战：本局还没有奖励')
        nav.state['no_reward_seen'] = True
        nav.click(info['give_up'])
        return False
    if nav.state.get('giving_up'):
        nav.log('  本局已有奖励，改为等这一轮打完')
    nav.state['giving_up'] = False
    nav.log('  从局内菜单继续游戏')
    nav.click(info['resume'])
    return False


@graph.handler('dungeon')
def on_dungeon(nav, scr, info):
    # 还在走向目标点说明第一波没开始，放弃不损失什么；局内菜单的「无奖励」会再确认一次
    if info.get('to_objective'):
        nav.log('  本局还没开打（轮次 %s），打开菜单离开' % info.get('round'))
        nav.state['giving_up'] = True
        nav.b.key('esc')
        return False
    if info.get('mode') and not nav.state.get('menu_checked'):
        # 驱离这类关卡看不出打到哪了，打开局内菜单看一眼：「无奖励」就离开，否则等它打完
        nav.log('  在%s里，看看局内菜单有没有奖励' % info['mode'])
        nav.state.update(giving_up=True, menu_checked=True)
        nav.b.key('esc')
        return False
    return wait_in_run(nav)


@graph.handler('blank_close')
def on_blank_close(nav, scr, info):
    nav.log('  点空白处关掉领奖弹窗（月卡等）')
    nav.b.click(0.50, 0.89)
    return False


@graph.handler('manual_popup')
def on_manual_popup(nav, scr, info):
    if info.get('before_run'):
        nav.log('  关掉开局前的委托手册弹窗，还没开局')
        nav.b.key('esc')
        return False
    return wait_in_run(nav)


@graph.handler('unknown')
@graph.handler('other_menu')
def on_unknown(nav, scr, info):
    if nav.state.get('loading') and nav.state.get('run_waits', 0) < MAX_RUN_WAITS:
        # 退出副本后的加载画面只有插图和提示，认不出是正常的
        nav.state['run_waits'] = nav.state.get('run_waits', 0) + 1
        return None
    # 多半是还在淡入的界面，先等一下再退
    if nav.wait(2) is None:
        return None
    nav.b.key('esc')
    return False


@graph.handler('boot')
def on_boot(nav, scr, info):
    # 启动画面之间的黑屏和进游戏前的加载画面都认不出，要等，不能按 Esc
    nav.state['loading'] = True
    if info['login']:
        nav.state['login_waits'] = nav.state.get('login_waits', 0) + 1
        if nav.state['login_waits'] > MAX_LOGIN_WAITS:
            raise NavError('游戏停在登录界面，请手动登录')
    return None


@graph.handler('title')
def on_title(nav, scr, info):
    nav.log('  点击进入游戏')
    nav.state['loading'] = True
    nav.click(info['enter'])
    return False


@graph.handler('boot_dialog')
def on_boot_dialog(nav, scr, info):
    # 启动时的弹窗（下载更新、网络错误……）不替用户做决定
    raise NavError('启动时弹出对话框：%s，请手动处理' % info['text'])


@graph.handler('commission')
def on_commission(nav, scr, info):
    if info['tab'] is None:
        # 页签还在动画中，或者鼠标停在某个页签上把它变成了金色
        if nav.wait(3) is None:
            if nav.unsure == 2:
                nav.b.park()
            return None
    return NotImplemented


@graph.handler('start')
def on_start(nav, scr, info):
    if info['via'] is None and info['mode'] is None and nav.wait(4) is None:
        return None
    g = nav.goal
    if g['screen'] != 'start':
        return NotImplemented
    if g['via'] == T.TABS[2] and info['via'] == T.TABS[2]:
        return pick_letter_entry(nav, info)
    entered = nav.state.get('entered_row')
    ok = start_matches(info, g)
    if entered and g['mode'] and info['mode'] and g['mode'] not in info['mode']:
        raise WrongMission(info['mode'], g['mode'])
    if g['via'] == T.TABS[1] and entered is None:
        # 同一个副本可能出现在好几行里，只有从目标行进来的才算
        ok = False
    if ok:
        return True
    same_dungeon = (not g['via'] or info['via'] == g['via']) and \
        (not g['mode'] or (info['mode'] and g['mode'] in info['mode']))
    if same_dungeon and g['lv'] and len(info['tiers']) > 1 and \
            not any(t['lv'] == g['lv'] for t in info['tiers']):
        raise NavError('%s 没有 Lv.%d，可选 %s' % (info['mode'], g['lv'], [t['lv'] for t in info['tiers']]))
    if ok is None:
        t = next(t for t in info['tiers'] if t['lv'] == g['lv'])
        nav.log('  选择 Lv.%d' % g['lv'])
        nav.b.click(TIER_X, t['y'])
        return False
    nav.state['entered_row'] = None
    nav.b.key('esc')
    return False


def pick_letter_entry(nav, info):
    """委托密函的开始界面左侧列着这一栏的几个委托，选中目标那个。"""
    g = nav.goal
    if g['column'] and info['column'] and g['column'] not in info['column']:
        nav.log('  栏位不对：%s' % info['column'])
        nav.b.key('esc')
        return False
    if info['mode'] and g['mode'] in info['mode']:
        return True
    entry = next((e for e in info['entries'] if g['mode'] in e['mode']), None)
    if entry is None:
        if g['column']:
            raise NavError('%s 栏现在是 %s，没有 %s' % (info['column'], [e['mode'] for e in info['entries']], g['mode']))
        nav.log('  %s 不在 %s 栏' % (g['mode'], info['column']))
        nav.b.key('esc')
        return False
    nav.log('  选择 %s' % entry['mode'])
    nav.b.click(LETTER_ENTRY_X, entry['y'])
    return False
