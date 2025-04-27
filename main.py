import json
import time
import argparse
import os
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from utils import reserve, get_user_credentials

get_current_time = lambda action: time.strftime("%H:%M:%S", time.localtime(time.time() + 8*3600)) if action else time.strftime("%H:%M:%S", time.localtime(time.time()))
get_current_dayofweek = lambda action: time.strftime("%A", time.localtime(time.time() + 8*3600)) if action else time.strftime("%A", time.localtime(time.time()))

SLEEPTIME = 0.0
ENABLE_SLIDER = True
MAX_ATTEMPT = 4
RESERVE_NEXT_DAY = False
TARGET_TIME = "22:00:00"  # 预约时间


def wait_until(target_time):
    """
    target_time 格式 "HH:MM:SS"，按本地+8 时区算今天的那个时刻。
    若已过，则立即返回；否则一次 sleep 到达。
    """
    # 解析 target_time
    h, m, s = map(int, target_time.split(':'))
    # 现在的本地时间（秒级）
    now = time.time()
    # 今天 00:00:00 的时间戳
    t0 = now - (time.localtime(now).tm_hour*3600 + time.localtime(now).tm_min*60 + time.localtime(now).tm_sec)
    # 目标今天的时间戳
    target_ts = t0 + h*3600 + m*60 + s
    # 如果已经过了，就直接返回
    if now >= target_ts:
        logging.info(f"到达目标时间 {target_time}，立即开始")
        return
    # 差值秒数
    wait_secs = target_ts - now
    logging.info(f"距离目标时间 {target_time} 还有 {wait_secs:.1f} 秒，sleep……")
    time.sleep(wait_secs)
    logging.info(f"到达目标时间 {target_time}，开始预约")

def login_all_users(users, usernames, passwords, action):
    sessions = []
    current_day = get_current_dayofweek(action)
    for idx, user in enumerate(users):
        username, password, times, roomid, seatid, days = user.values()
        if action:
            username, password = usernames.split(',')[idx], passwords.split(',')[idx]

        if current_day not in days:
            logging.info(f"User {username}: 今天不预约，跳过")
            sessions.append(None)
            continue

        logging.info(f"User {username}: 提前登录中...")
        s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT,
                    enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
        s.get_login_status()
        s.login(username, password)
        s.requests.headers.update({'Host': 'office.chaoxing.com'})
        sessions.append(s)
    return sessions

def reserve_once(users, sessions, action):
    """只跑一轮预约"""
    current_day = get_current_dayofweek(action)
    success_list = [False] * len(users)

    for idx, user in enumerate(users):
        username, _, times, roomid, seatid, days = user.values()
        if current_day not in days or not sessions[idx]:
            continue

        logging.info(f"开始预约 - 用户 {username} -- {times} -- 座位 {seatid}")
        success_list[idx] = sessions[idx].submit(times, roomid, seatid, action)

    return success_list

def main(users, action=False):
    logging.info(f"程序启动，立即登录 (action={'on' if action else 'off'})")

    usernames, passwords = (None, None)
    if action:
        usernames, passwords = get_user_credentials(action)

    # 提前登录
    sessions = login_all_users(users, usernames, passwords, action)

    # 等待到预约时间
    wait_until(TARGET_TIME)

    # 一轮预约
    success_list = reserve_once(users, sessions, action)
    logging.info(f"一轮预约结束，结果：{success_list}")

def debug(users, action=False):
    # 保持原 debug 行为
    logging.info("Debug 模式")
    usernames, passwords = (None, None)
    if action:
        usernames, passwords = get_user_credentials(action)

    current_day = get_current_dayofweek(action)
    for idx, user in enumerate(users):
        username, password, times, roomid, seatid, days = user.values()
        if action:
            username, password = usernames.split(',')[idx], passwords.split(',')[idx]
        if current_day not in days:
            continue
        s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT,
                    enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
        s.get_login_status()
        s.login(username, password)
        s.requests.headers.update({'Host': 'office.chaoxing.com'})
        s.submit(times, roomid, seatid, action)

def get_roomid(_a, _b):
    username = input("请输入用户名：")
    password = input("请输入密码：")
    s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT,
                enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
    s.get_login_status()
    s.login(username, password)
    s.requests.headers.update({'Host': 'office.chaoxing.com'})
    encode = input("请输入deptldEnc：")
    s.roomid(encode)

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    parser = argparse.ArgumentParser(prog='ChaoXingReserveSeat')
    parser.add_argument('-u','--user', default=config_path, help='用户配置文件')
    parser.add_argument('-m','--method', default="reserve", choices=["reserve","debug","room"])
    parser.add_argument('-a','--action', action="store_true", help='GitHub Action 模式')
    args = parser.parse_args()

    with open(args.user, "r") as f:
        usersdata = json.load(f)["reserve"]
    if args.method == "reserve":
        main(usersdata, args.action)
    elif args.method == "debug":
        debug(usersdata, args.action)
    else:
        get_roomid(None, None)

