import json
import time
import argparse
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 日志记录配置 ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- 从 utils 导入模块 ---
from utils import reserve, get_user_credentials

# --- 时间获取函数 (无pytz依赖) ---
get_current_time = lambda action: (
    time.strftime("%H:%M:%S", time.localtime(time.time() + 8 * 3600))
    if action
    else time.strftime("%H:%M:%S", time.localtime(time.time()))
)
get_current_dayofweek = lambda action: (
    time.strftime("%A", time.localtime(time.time() + 8 * 3600))
    if action
    else time.strftime("%A", time.localtime(time.time()))
)

# --- 🔥 全局配置 ---
LOGIN_TIME = "16:9:30"
RESERVE_TIME = "16:10:00"
ENDTIME = "16:12:00"

SLEEPTIME = 0.2
ENABLE_SLIDER = True
MAX_ATTEMPT = 5
# 🔥 关键修改：确保脚本预约当天
RESERVE_NEXT_DAY = False

def wait_until(target_time_str, action):
    """等待直到指定的时间"""
    logging.info(f"等待北京时间 {target_time_str}...")
    while get_current_time(action) < target_time_str:
        time.sleep(0.5)
    logging.info(f"已到达指定时间 {target_time_str}，继续执行。")


def _iter_todays_tasks(user_dict, current_dayofweek):
    """遍历并返回今天需要执行的任务"""
    tasks = user_dict.get("tasks", [])
    for t in tasks:
        if current_dayofweek in t.get("daysofweek", []):
            yield t.get("time"), t.get("roomid"), t.get("seatid")


def login_and_reserve(users, usernames, passwords, action, success_states=None):
    """
    按顺序处理每个用户，但对单个用户的多个任务进行并行预约。
    """
    if success_states is None:
        success_states = {} # 使用字典来跟踪每个任务的成功状态

    current_dayofweek = get_current_dayofweek(action)

    for index, user in enumerate(users):
        username = user.get("username")
        if action:
            username = usernames.split(",")[index]

        # 检查该用户的所有任务是否都已成功
        todays_tasks = list(_iter_todays_tasks(user, current_dayofweek))
        user_task_status = success_states.get(username, {})
        if todays_tasks and all(user_task_status.get(tuple(t[0]), False) for t in todays_tasks):
            continue

        password = user.get("password")
        if action:
            password = passwords.split(",")[index]

        if not todays_tasks:
            continue

        # 为每个用户登录一次
        s = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=RESERVE_NEXT_DAY,
        )
        login_ok, _ = s.login(username, password)
        if not login_ok:
            continue
        
        # 🔥 对该用户的所有任务进行并行抢座
        with ThreadPoolExecutor(max_workers=len(todays_tasks)) as executor:
            future_to_task = {}
            if username not in success_states:
                success_states[username] = {}

            for times, roomid, seatid in todays_tasks:
                # 只提交尚未成功的任务
                if not success_states[username].get(tuple(times), False):
                    if isinstance(seatid, str):
                        seatid = [seatid]
                    logging.info(f"--- 提交并行任务: {username} -- {times} -- {seatid} ---")
                    future = executor.submit(s.submit, times, roomid, seatid, action)
                    future_to_task[future] = times

            for future in as_completed(future_to_task):
                times = future_to_task[future]
                try:
                    if future.result():
                        success_states[username][tuple(times)] = True
                        logging.info(f"� 并行任务成功: {username} -- {times}")
                    else:
                        success_states[username][tuple(times)] = False
                except Exception as e:
                    logging.error(f"并行任务异常: {username} -- {times} -- {e}")
                    success_states[username][tuple(times)] = False
    
    return success_states


def main(users, action=False):
    """主执行函数"""
    logging.info(f"🎬 程序启动，将在 {LOGIN_TIME} 开始登录...")
    wait_until(LOGIN_TIME, action)

    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)

    wait_until(RESERVE_TIME, action)
    logging.info("========== 🎯 开始执行预约任务 ==========")

    attempt_times = 0
    success_states = None

    current_dayofweek = get_current_dayofweek(action)
    today_user_num = sum(1 for u in users if any(_iter_todays_tasks(u, current_dayofweek)))

    if today_user_num == 0:
        logging.info("🌟 今天没有需要执行的预约任务，程序结束。")
        return

    while get_current_time(action) < ENDTIME:
        attempt_times += 1
        success_states = login_and_reserve(
            users, usernames, passwords, action, success_states
        )
        
        # 检查所有用户的任务是否都已完成
        successful_users = 0
        for user in users:
            username = user.get("username")
            todays_tasks = list(_iter_todays_tasks(user, current_dayofweek))
            if not todays_tasks: continue

            user_task_status = success_states.get(username, {})
            if all(user_task_status.get(tuple(t[0]), False) for t in todays_tasks):
                successful_users += 1

        logging.info(
            f"第 {attempt_times} 轮尝试结束, "
            f"已完成全部任务的用户: {successful_users}/{today_user_num}, "
            f"当前时间 {get_current_time(action)}"
        )

        if successful_users >= today_user_num:
            logging.info("🎉 所有需要预约的用户均已成功！")
            return

        time.sleep(1)

    logging.warning(f"🏁 抢座时间已过 ({ENDTIME})，程序结束。")


def debug(users, action=False):
    """调试模式"""
    logging.info("--- 🔧 调试模式启动 ---")
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)
    login_and_reserve(users, usernames, passwords, action)
    logging.info("--- 🔧 调试模式结束 ---")


if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    parser = argparse.ArgumentParser(prog="Chao Xing seat auto reserve")
    parser.add_argument("-u", "--user", default=config_path, help="user config file")
    parser.add_argument(
        "-m", "--method", default="reserve", choices=["reserve", "debug"]
    )
    parser.add_argument("-a", "--action", action="store_true")
    args = parser.parse_args()

    try:
        with open(args.user, "r", encoding="utf-8") as data:
            usersdata = json.load(data)["reserve"]
    except Exception as e:
        logging.error(f"💥 配置文件加载失败: {e}")
        exit(1)

    if args.method == "reserve":
        main(usersdata, args.action)
    else:
        debug(usersdata, args.action)
�
