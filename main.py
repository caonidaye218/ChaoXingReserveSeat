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

# --- 🔥 全局配置 ---
# 你可以在这里设置定时和抢座参数
LOGIN_TIME = "21:58:30"   # 脚本将等待到这个时间点才开始登录
RESERVE_TIME = "22:00:00" # 登录后，将等待到这个时间点才开始抢座
ENDTIME = "22:02:00"      # 抢座循环将在这个时间点后结束

SLEEPTIME = 0.2           # 每次抢座失败后的间隔
ENABLE_SLIDER = True      # 是否有滑块验证
MAX_ATTEMPT = 5           # 每个座位的最大尝试次数
RESERVE_NEXT_DAY = False  # 🔥 已设置为 False，预约当天座位

def wait_until(target_time_str, action):
    """等待直到指定的时间"""
    logging.info(f"等待直到北京时间 {target_time_str}...")
    while get_current_time(action) < target_time_str:
        time.sleep(1)
    logging.info(f"已到达指定时间 {target_time_str}，继续执行。")


def login_and_reserve(users, usernames, passwords, action, success_list=None):
    """
    核心的登录和预约函数，保留了你原始的逻辑。
    为尚未成功的用户尝试预约。
    """
    if success_list is None:
        success_list = [False] * len(users)
        
    current_dayofweek = get_current_dayofweek(action)

    for index, user in enumerate(users):
        # 如果该用户已预约成功，则跳过
        if success_list[index]:
            continue

        username, password, times, roomid, seatid, daysofweek = user.values()
        
        if action:
            username, password = (
                usernames.split(",")[index],
                passwords.split(",")[index],
            )
        
        if current_dayofweek not in daysofweek:
            # 对于今天不需要预约的用户，我们将其标记为成功，以防主循环卡住
            success_list[index] = True
            continue

        logging.info(f"----------- {username} -- {times} -- {seatid} try -----------")
        
        s = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=RESERVE_NEXT_DAY,
        )
        s.get_login_status()
        s.login(username, password)
        s.requests.headers.update({"Host": "office.chaoxing.com"})
        
        suc = s.submit(times, roomid, seatid, action)
        success_list[index] = suc
        
    return success_list


def main(users, action=False):
    """主执行函数，包含定时和分流逻辑"""
    logging.info(f"🎬 程序启动，将在 {LOGIN_TIME} 开始登录...")

    # 1. 定时功能：等待到登录时间
    wait_until(LOGIN_TIME, action)
    
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)
    
    # 2. 定时功能：等待到抢座时间
    wait_until(RESERVE_TIME, action)
    
    logging.info("========== 🎯 开始执行预约任务 ==========")
    
    attempt_times = 0
    success_list = None
    
    current_dayofweek = get_current_dayofweek(action)
    today_reservation_num = sum(
        1 for d in users if current_dayofweek in d.get("daysofweek", [])
    )
    if today_reservation_num == 0:
        logging.info("🌟 今天没有需要执行的预约任务，程序结束。")
        return

    # 3. 分流机制：循环抢座直到 ENDTIME
    while get_current_time(action) < ENDTIME:
        attempt_times += 1
        
        try:
            success_list = login_and_reserve(
                users, usernames, passwords, action, success_list
            )
        except Exception as e:
            logging.error(f"在第 {attempt_times} 轮尝试中发生错误: {e}")

        successful_count = sum(1 for s in success_list if s)
        logging.info(
            f"第 {attempt_times} 轮尝试结束, "
            f"成功 {successful_count}/{today_reservation_num}, "
            f"当前时间 {get_current_time(action)}"
        )
        
        if successful_count >= today_reservation_num:
            logging.info("🎉 全部预约成功！")
            return
        
        time.sleep(1) # 每轮结束后短暂休息

    logging.warning(f"🏁 抢座时间已过 ({ENDTIME})，程序结束。")


def debug(users, action=False):
    """调试模式，立即执行一次"""
    logging.info("--- 🔧 调试模式启动 ---")
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)

    # 调试模式下直接调用一次预约函数
    login_and_reserve(users, usernames, passwords, action)
    logging.info("--- 🔧 调试模式结束 ---")


def get_roomid(args1, args2):
    """获取房间ID的功能，保留你原始版本"""
    username = input("请输入用户名：")
    password = input("请输入密码：")
    s = reserve(
        sleep_time=SLEEPTIME,
        max_attempt=MAX_ATTEMPT,
        enable_slider=ENABLE_SLIDER,
        reserve_next_day=RESERVE_NEXT_DAY,
    )
    s.get_login_status()
    s.login(username=username, password=password)
    s.requests.headers.update({"Host": "office.chaoxing.com"})
    encode = input("请输入deptldEnc：")
    s.roomid(encode)


if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    parser = argparse.ArgumentParser(prog="Chao Xing seat auto reserve")
    parser.add_argument("-u", "--user", default=config_path, help="user config file")
    parser.add_argument(
        "-m",
        "--method",
        default="reserve",
        choices=["reserve", "debug", "room"],
        help="reserve (定时), debug (立即), room (获取房间ID)",
    )
    parser.add_argument(
        "-a",
        "--action",
        action="store_true",
        help="启用 GitHub Actions 模式",
    )
    args = parser.parse_args()
    
    func_dict = {"reserve": main, "debug": debug, "room": get_roomid}

    if args.method in ["reserve", "debug"]:
        try:
            with open(args.user, "r", encoding="utf-8") as data:
                usersdata = json.load(data)["reserve"]
            func_dict[args.method](usersdata, args.action)
        except Exception as e:
            logging.error(f"💥 配置文件加载或执行出错: {e}")
            exit(1)
    else:
        # 调用 get_roomid
        func_dict[args.method](None, None)
