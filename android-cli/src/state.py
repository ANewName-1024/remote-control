#!/usr/bin/env python3
"""状态机 - 页面导航状态管理"""

from enum import Enum
from typing import Optional, Callable


class PageState(Enum):
    UNKNOWN = "unknown"
    HOME = "home"                  # 小红书首页/推荐
    EXPLORE = "explore"            # 发现页
    SEARCH = "search"              # 搜索页
    NOTE_DETAIL = "note_detail"    # 笔记详情页
    PROFILE = "profile"            # 个人主页
    PROFILE_EDIT = "profile_edit"  # 编辑资料页
    PUBLISH_PAGE = "publish_page"  # 发布页
    SETTINGS = "settings"          # 设置页


class StateMachine:
    """状态机 - 在执行操作前校验当前页面状态"""

    # 合法的状态转换
    TRANSITIONS = {
        (PageState.HOME, PageState.SEARCH): "click_search",
        (PageState.HOME, PageState.NOTE_DETAIL): "click_note",
        (PageState.HOME, PageState.PROFILE): "click_profile",
        (PageState.HOME, PageState.PUBLISH_PAGE): "click_publish",
        (PageState.SEARCH, PageState.NOTE_DETAIL): "click_search_result",
        (PageState.NOTE_DETAIL, PageState.HOME): "press_back",
        (PageState.PROFILE, PageState.PROFILE_EDIT): "click_edit_profile",
        (PageState.PROFILE_EDIT, PageState.PROFILE): "save_profile",
        (PageState.PUBLISH_PAGE, PageState.HOME): "publish_success",
    }

    def __init__(self):
        self.current_state = PageState.UNKNOWN
        self.history = []

    def detect(self, activity_name: str) -> PageState:
        """根据 Activity 名称判断页面状态"""
        activity_name = activity_name.lower()

        if "indexactivity" in activity_name or "mainactivity" in activity_name:
            return PageState.HOME
        elif "searchactivity" in activity_name:
            return PageState.SEARCH
        elif "detail" in activity_name or "note" in activity_name:
            return PageState.NOTE_DETAIL
        elif "profile" in activity_name or "mine" in activity_name:
            return PageState.PROFILE
        elif "edit" in activity_name or "modify" in activity_name:
            return PageState.PROFILE_EDIT
        elif "publish" in activity_name or "post" in activity_name:
            return PageState.PUBLISH_PAGE
        elif "settings" in activity_name or "setting" in activity_name:
            return PageState.SETTINGS
        else:
            return PageState.UNKNOWN

    def can_transition(self, from_state: PageState, to_state: PageState, action: str) -> bool:
        """检查状态转换是否合法"""
        key = (from_state, to_state)
        if key in self.TRANSITIONS:
            return self.TRANSITIONS[key] == action
        # 未定义的转换默认允许（保守策略）
        return True

    def execute(self, action: str, operation: Callable, from_state: PageState, to_state: PageState):
        """
        执行操作（带状态校验）

        Args:
            action: 操作名称
            operation: 要执行的操作函数
            from_state: 操作前的状态
            to_state: 操作后的预期状态

        Returns:
            操作结果，或 "CANCELLED" 或 "ERROR"
        """
        # 校验转换合法性
        if not self.can_transition(from_state, to_state, action):
            print(f"[WARN] 状态转换不合法: {from_state.value} --({action})--> {to_state.value}")
            response = input("是否继续？ (y/n): ")
            if response.lower() != "y":
                return "CANCELLED"

        # 执行操作
        try:
            result = operation()
            self.history.append(self.current_state)
            self.current_state = to_state
            return result
        except Exception as e:
            print(f"[ERROR] 操作执行失败: {e}")
            return "ERROR"

    def get_state(self) -> PageState:
        return self.current_state

    def reset(self):
        self.current_state = PageState.UNKNOWN
        self.history.clear()
