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

# --- 时间获取函数 (使用你原始版本的方式，无pytz依赖) ---
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

# --- 🔥 全局配置（保持原有逻辑与命名，仅做最小改动） ---
LOGIN_TIME = "21:58:30"  # 脚本将等待到这个时间点才开始登录
RESERVE_TIME = "22:00:00" # 登录后，将等待到这个时间点才开始抢座
ENDTIME = "22:02:00"      # 抢座循环将在这个时间点后结束

SLEEPTIME = 0.2           # 每次抢座失败后的间隔
ENABLE_SLIDER = True      # 是否有滑块验证
MAX_ATTEMPT = 5           # 每个座位的最大尝试次数
RESERVE_NEXT_DAY = False  # 🔥 已设置为 False，默认预约当天座位（与原逻辑一致）

def wait_until(target_time_str, action):
    """等待直到指定的时间"""
    logging.info(f"等待北京时间 {target_time_str}...")
    while get_current_time(action) < target_time_str:
        time.sleep(0.2)
    logging.info(f"已到达指定时间 {target_time_str}，继续执行。")


def _iter_todays_tasks(user_dict, current_dayofweek):
    """
    适配 config.json 的新结构：每个用户下有 tasks 列表。
    只产出“今天需要执行”的任务项（包含 times, roomid, seatid_list）。
    """
    tasks = user_dict.get("tasks", [])
    for t in tasks:
        daysofweek = t.get("daysofweek", [])
        if current_dayofweek in daysofweek:
            times = t.get("time")
            roomid = t.get("roomid")
            seatid = t.get("seatid")
            yield times, roomid, seatid


def login_and_reserve(users, usernames, passwords, action, success_list=None):
    """
    登录并尝试预约（只做必要修改：从 user.values() 改为读取 tasks）
    - 对每个用户：遍历“今天的任务”，任一任务成功则视为该用户成功。
    """
    if success_list is None:
        success_list = [False] * len(users)

    current_dayofweek = get_current_dayofweek(action)

    for index, user in enumerate(users):
        # 如果该用户已预约成功，则跳过
        if success_list[index]:
            continue

        # 读取账号与密码（支持 Actions 与本地两种来源）
        username = user.get("username")
        password = user.get("password")
        if action:
            username, password = (
                usernames.split(",")[index],
                passwords.split(",")[index],
            )

        # 列出今天需要执行的任务
        todays_tasks = list(_iter_todays_tasks(user, current_dayofweek))
        if not todays_tasks:
            # 今天该用户没有任务 → 标记为“无需执行”，避免主循环卡住
            success_list[index] = True
            continue

        # 登录会话（与原逻辑一致）
        s = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=RESERVE_NEXT_DAY,
        )
        s.get_login_status()
        s.login(username, password)
        s.requests.headers.update({"Host": "office.chaoxing.com"})

        # 依次尝试今天的每个任务（任一成功即可）
        for times, roomid, seatid in todays_tasks:
            # seatid 允许为字符串或列表，统一转列表交给 reserve.submit
            if isinstance(seatid, str):
                seatid = [seatid]

            logging.info(f"----------- {username} -- {times} -- {seatid} try -----------")
            suc = s.submit(times, roomid, seatid, action)
            if suc:
                success_list[index] = True
                break  # 该用户已成功，进入下一个用户

    return success_list


def main(users, action=False):
    """主执行函数（定时与分流逻辑保持不变，仅替换任务结构读取方式）"""
    logging.info(f"🎬 程序启动，将在 {LOGIN_TIME} 开始登录...")

    # 1. 等待到登录时间
    wait_until(LOGIN_TIME, action)

    # 2. 获取 Actions 凭证（如启用）
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)

    # 3. 等待到抢座时间
    wait_until(RESERVE_TIME, action)

    logging.info("========== 🎯 开始执行预约任务 ==========")

    attempt_times = 0
    success_list = None

    # 4. 计算今天需要执行的“用户任务数”（即今天有任务的用户数量）
    current_dayofweek = get_current_dayofweek(action)
    today_reservation_num = 0
    for u in users:
        # 只要该用户 tasks 里有任何一条包含今天，就计数一次
        if any(current_dayofweek in t.get("daysofweek", []) for t in u.get("tasks", [])):
            today_reservation_num += 1

    if today_reservation_num == 0:
        logging.info("🌟 今天没有需要执行的预约任务，程序结束。")
        return

    # 5. 分流机制：循环抢座直到 ENDTIME
    while get_current_time(action) < ENDTIME:
        attempt_times += 1

        try:
            success_list = login_and_reserve(
                users, usernames, passwords, action, success_list
            )
        except Exception as e:
            logging.error(f"在第 {attempt_times} 轮尝试中发生错误: {e}")

        # 只统计“今天有任务的用户”中的成功数
        successful_count = 0
        for idx, ok in enumerate(success_list):
            if not ok:
                continue
            u = users[idx]
            if any(current_dayofweek in t.get("daysofweek", []) for t in u.get("tasks", [])):
                successful_count += 1

        logging.info(
            f"第 {attempt_times} 轮尝试结束, "
            f"成功 {successful_count}/{today_reservation_num}, "
            f"当前时间 {get_current_time(action)}"
        )

        if successful_count >= today_reservation_num:
            logging.info("🎉 今天所有需要执行的用户均已预约成功！")
            return

        time.sleep(1)  # 每轮结束后短暂休息

    logging.warning(f"🏁 抢座时间已过 ({ENDTIME})，程序结束。")


def debug(users, action=False):
    """调试模式：立即尝试今天的任务（只做必要修改：读取 tasks）"""
    logging.info("--- 🔧 调试模式启动 ---")
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)

    current_dayofweek = get_current_dayofweek(action)

    for index, user in enumerate(users):
        username = user.get("username")
        password = user.get("password")
        if action:
            username, password = (
                usernames.split(",")[index],
                passwords.split(",")[index],
            )

        # 今天的任务
        todays_tasks = list(_iter_todays_tasks(user, current_dayofweek))
        if not todays_tasks:
            logging.info("今天该用户没有任务，跳过。")
            continue

        logging.info(f"----------- {username} 调试尝试，今日任务数 {len(todays_tasks)} -----------")
        s = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=RESERVE_NEXT_DAY,
        )
        s.get_login_status()
        s.login(username, password)
        s.requests.headers.update({"Host": "office.chaoxing.com"})

        for times, roomid, seatid in todays_tasks:
            if isinstance(seatid, str):
                seatid = [seatid]
            suc = s.submit(times, roomid, seatid, action)
            if suc:
                logging.info(f"✅ 用户 {username} 调试成功（{times}/{roomid}/{seatid}）！")
                return


if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    parser = argparse.ArgumentParser(prog="Chao Xing seat auto reserve")
    parser.add_argument("-u", "--user", default=config_path, help="user config file")
    parser.add_argument(
        "-m",
        "--method",
        default="reserve",
        choices=["reserve", "debug"],
        help="reserve (定时) 或 debug (立即)",
    )
    parser.add_argument(
        "-a",
        "--action",
        action="store_true",
        help="启用 GitHub Actions 模式",
    )
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
