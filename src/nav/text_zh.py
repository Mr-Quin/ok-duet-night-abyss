"""简体中文客户端的界面文字。

导航层从画面上读的字都在这里。换其他语言的客户端时复制一份这个模块、重新采集
atlas，不需要改导航逻辑。
"""

TABS = ['委托', '夜航手册', '委托密函', '悬赏委托']
SECTIONS = ['今日行程', '委托', '梦魔残声', '歧路足音']
BOOK_TITLE = '夜航手册'
BOOK_MARKERS = ('历练', '今日行程', '歧路足音')

# 委托页卡片从左到右的顺序
MISSIONS = ['勘察/无尽', '避险', '驱逐', '探险/无尽', '调停', '驱离', '护送', '追缉', '扼守/无尽', '迁移']
LETTER_COLUMNS = ('角色', '武器', '魔之楔')

GO = '前往'
GO_CHALLENGE = '前往挑战'
DROPS = '击杀可能获得'
DROP_WORDS = ('击杀', '获得')

UID = 'UID'
SHOP = '商店'
EVENTS = '活动'
ESC = 'ESC'
BACK = '返回'
LV = 'Lv'

START = ('开始挑战', '确认选择', '匹配挑战')
EXIT_CONFIRM = '是否结束当前任务'
CANCEL = '取消'
RESULT = '委托完成'
RESULT_BUTTONS = ('再次进行', '退出委托')
RETREAT = '撤离'
CONTINUE = '继续挑战'
AUTO_RUNNING = '轮次中'
AUTO_LABEL = '自动轮次'
AUTO_ROUNDS = r'轮次\s*(\d+)\s*/\s*99'
GIVE_UP = '放弃挑战'
RESUME = '继续游戏'
MANUAL_SKIP = '不使用'
ROUND_HUD = ('当前轮次', '波次')
ROUND_NOW = r'当前轮次\s*[:：]?\s*(\d+)'
TO_OBJECTIVE = '前往目标点'
NO_REWARD = '无奖励'
CONFIRM = '确定'

# 从手册分区进入的页面：名称 -> (分区, 入口按钮文字)
PAGE_ENTRY = {'迷津': ('歧路足音', GO), 'boss_map': ('梦魔残声', GO_CHALLENGE)}

