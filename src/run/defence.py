"""扼守：先走到防守点，再在防守范围里打。

走的部分按出生点认路线：认得的重放录好的路线，认不得的按目标标记走，走到了就记成新路线。
"""
import os
import time

from src.tasks.fullauto import routes
from src.tasks.fullauto.marker_walk import MarkerWalk
from src.tasks.fullauto.minimap import MapLibrary

RESET_WAVE_WAIT = 25


class Defence:
    name = '扼守'
    names = ('扼守',)
    uses_rounds = True

    def __init__(self, task):
        self.task = task
        self.maps = None
        self.routes = None
        self.wave, self.wave_since = -1, 0

    def begin(self):
        """一局开始：走到防守点。返回 False 表示没走到、已经放弃了这一局。"""
        task = self.task
        task.reset_wave_info()
        task.skill_tick.reset()
        if not self.walk():
            # 已经走了一段，离目标点旁的复位点最近
            if not task.reset_and_transport() or not self.wave_started(RESET_WAVE_WAIT):
                task.log_info("复位后也没开始波次，放弃这一局")
                task.give_up_mission()
                return False
        self.wave, self.wave_since = task.current_wave, time.time()
        return True

    def tick(self):
        """在防守范围里打。返回 False 表示波次超时、已经放弃了这一局。"""
        task = self.task
        task.get_wave_info()
        in_combat = task.current_wave != -1
        if task.current_wave != self.wave:
            self.wave, self.wave_since = task.current_wave, time.time()
        # 读不出波次时也要计时，不然一直读不出就永远不会超时
        if task.combat_detection_enabled() and time.time() - self.wave_since >= task.config.get("超时时间", 120):
            task.log_info("波次超时，放弃这一局")
            task.give_up_mission()
            return False
        if task.skills_ready(in_combat):
            task.skill_tick()
        return True

    def next_round(self):
        self.wave, self.wave_since = -1, time.time()
        self.task.reset_wave_info()

    def wave_started(self, timeout=3):
        """到了目标点波次就会开始；没开始说明其实没到（比如距离读错了）。"""
        task = self.task
        task.current_wave = -1
        if task.wait_until(lambda: task.current_wave != -1, post_action=task.get_wave_info, time_out=timeout):
            return True
        task.log_info("走到了但波次没开始")
        return False

    def reach(self, walker, seen):
        if walker.run(seen) and self.wave_started():
            return True
        # 有的图防守范围比 6 米小，停下来时还在范围外
        seen = walker.wait_for_marker(timeout=1)
        return seen is not None and walker.run(seen, arrive=2) and self.wave_started()

    def identify_map(self):
        if self.maps is None:
            self.maps = MapLibrary()
        name, score = self.maps.identify(self.task.next_frame())
        self.task.log_info(f"地图 {name or '未知'}（{score:.2f}）")
        return name

    def walk(self):
        task = self.task
        map_name = self.identify_map()
        walker = MarkerWalk(task)
        seen = walker.wait_for_marker()
        if seen is None:
            task.log_info("没找到目标标记")
            task.screenshot("walk_no_marker")
            return False
        if self.routes is None:
            self.routes = routes.RouteLibrary()
        spawn, marker = task.next_frame(), (seen[0], walker.last_y)
        route = self.routes.find(spawn, marker, map_name)
        if route is not None:
            task.log_info(f"按路线 {route.name} 走")
            routes.play(task, route)
            seen = walker.wait_for_marker(timeout=3)
            if seen is not None and self.reach(walker, seen):
                self.routes.remember_map(route, map_name)
                return True
            if route.path.startswith(routes.LEARNED_DIR):
                # 学来的路线这次没走到，删掉，下次重新学
                os.remove(route.path)
                self.routes.routes.remove(route)
            return False
        near, score, offset = self.routes.closest(spawn, marker)
        if near is not None:
            task.log_info(f"没有对上的路线，最像 {near.name}：画面 {score:.2f}，标记差 {offset:.3f}")
        if self.reach(walker, seen):
            path = self.routes.save(spawn, marker, walker.steps, map_name)
            task.log_info(f"记下这条路线：{os.path.basename(path)}")
            return True
        return False
