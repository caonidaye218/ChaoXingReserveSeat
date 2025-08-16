import json
import time
import argparse
import os
import logging

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
LOGIN_TIME = "16:13:30"
RESERVE_TIME = "16:13:00"
ENDTIME = "22:02:00"

SLEEPTIME = 0.8  # 增加每次尝试的间隔，降低请求频率
ENABLE_SLIDER = True
MAX_ATTEMPT = 8  # 增加最大尝试次数
RESERVE_NEXT_DAY = False # 固定预约当天

def wait_until(target_time_str, action):
    """等待直到指定的时间"""
    logging.info(f"等待北京时间 {target_time_str}...")
    while get_current_time(action) < target_time_str:
        time.sleep(0.5)
    logging.info(f"已到达指定时间 {target_time_str}，继续执行。")

def _iter_todays_tasks(user_dict, current_dayofweek):
    """遍历并返回今天需要执行的任务"""
    for t in user_dict.get("tasks", []):
        if current_dayofweek in t.get("daysofweek", []):
            yield t.get("time"), t.get("roomid"), t.get("seatid")

def login_and_reserve(users, usernames, passwords, action, success_list=None):
    """按顺序处理每个用户"""
    if success_list is None:
        success_list = [False] * len(users)

    current_dayofweek = get_current_dayofweek(action)

    for index, user in enumerate(users):
        if success_list[index]:
            continue

        username = user.get("username")
        password = user.get("password")
        if action:
            username, password = usernames.split(",")[index], passwords.split(",")[index]

        todays_tasks = list(_iter_todays_tasks(user, current_dayofweek))
        if not todays_tasks:
            success_list[index] = True
            continue

        s = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=RESERVE_NEXT_DAY,
        )
        login_ok, _ = s.login(username, password)
        if not login_ok:
            continue

        for times, roomid, seatid in todays_tasks:
            if isinstance(seatid, str):
                seatid = [seatid]
            
            logging.info(f"----------- {username} -- {times} -- {seatid} try -----------")
            suc = s.submit(times, roomid, seatid, action)
            if suc:
                success_list[index] = True
                logging.info(f"🎉 用户 {username} 预约成功！")
                break 

    return success_list

def main(users, action=False):
    """主执行函数"""
    logging.info(f"🎬 程序启动，将在 {LOGIN_TIME} 开始登录...")
    wait_until(LOGIN_TIME, action)

    usernames, passwords = get_user_credentials(action) if action else (None, None)

    wait_until(RESERVE_TIME, action)
    logging.info("========== 🎯 开始执行预约任务 ==========")

    attempt_times = 0
    success_list = None
    current_dayofweek = get_current_dayofweek(action)
    today_reservation_num = sum(1 for u in users if any(_iter_todays_tasks(u, current_dayofweek)))

    if today_reservation_num == 0:
        logging.info("🌟 今天没有需要执行的预约任务，程序结束。")
        return

    while get_current_time(action) < ENDTIME:
        attempt_times += 1
        try:
            success_list = login_and_reserve(users, usernames, passwords, action, success_list)
        except Exception as e:
            logging.error(f"在第 {attempt_times} 轮尝试中发生错误: {e}")

        successful_count = sum(1 for s in success_list if s)
        logging.info(f"第 {attempt_times} 轮尝试结束, 成功 {successful_count}/{today_reservation_num}, 当前时间 {get_current_time(action)}")

        if successful_count >= today_reservation_num:
            logging.info("🎉 所有需要预约的用户均已成功！")
            return
        
        time.sleep(1)

    logging.warning(f"🏁 抢座时间已过 ({ENDTIME})，程序结束。")

def debug(users, action=False):
    """调试模式"""
    logging.info("--- 🔧 调试模式启动 ---")
    usernames, passwords = get_user_credentials(action) if action else (None, None)
    login_and_reserve(users, usernames, passwords, action)
    logging.info("--- 🔧 调试模式结束 ---")

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    parser = argparse.ArgumentParser(prog="Chao Xing seat auto reserve")
    parser.add_argument("-u", "--user", default=config_path, help="user config file")
    parser.add_argument("-m", "--method", default="reserve", choices=["reserve", "debug"])
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
