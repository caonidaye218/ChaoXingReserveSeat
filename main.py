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
ENDTIME = "22:03:00"
ENABLE_SLIDER = True
MAX_ATTEMPT = 3
RESERVE_NEXT_DAY = True
TARGET_TIME = "22:00:00"  # ✅ 预约时间

def wait_until(target_time):
    while True:
        current_time = get_current_time(True)
        if current_time >= target_time:
            logging.info(f"到达目标时间 {target_time}，开始预约")
            break
        logging.info(f"当前时间 {current_time}，等待目标时间 {target_time}")
        time.sleep(10)

def login_all_users(users, usernames, passwords, action):
    sessions = []
    current_dayofweek = get_current_dayofweek(action)
    for index, user in enumerate(users):
        username, password, times, roomid, seatid, daysofweek = user.values()
        if action:
            username, password = usernames.split(',')[index], passwords.split(',')[index]

        if current_dayofweek not in daysofweek:
            logging.info(f"User {username}: 今天不预约，跳过登录")
            sessions.append(None)
            continue

        logging.info(f"User {username}: 提前登录中...")
        s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
        s.get_login_status()
        s.login(username, password)
        s.requests.headers.update({'Host': 'office.chaoxing.com'})
        sessions.append(s)

    return sessions

def reserve_with_sessions(users, sessions, action, success_list=None):
    if success_list is None:
        success_list = [False] * len(users)

    current_dayofweek = get_current_dayofweek(action)
    for index, user in enumerate(users):
        username, _, times, roomid, seatid, daysofweek = user.values()

        if current_dayofweek not in daysofweek:
            continue

        if not success_list[index] and sessions[index]:
            logging.info(f"开始预约 - 用户 {username} -- {times} -- 座位 {seatid}")
            suc = sessions[index].submit(times, roomid, seatid, action)
            success_list[index] = suc

    return success_list

def main(users, action=False):
    logging.info(f"程序启动，立即登录 (action={'on' if action else 'off'})")

    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)

    # 1. 提前登录所有账号
    sessions = login_all_users(users, usernames, passwords, action)

    # 2. 登录完成后，等待到目标预约时间
    wait_until(TARGET_TIME)

    # 3. 到点开始预约
    attempt_times = 0
    current_time = get_current_time(action)
    current_dayofweek = get_current_dayofweek(action)
    today_reservation_num = sum(1 for d in users if current_dayofweek in d.get('daysofweek'))
    success_list = None

    while current_time < ENDTIME:
        attempt_times += 1
        success_list = reserve_with_sessions(users, sessions, action, success_list)
        logging.info(f"尝试次数 {attempt_times}, 当前时间 {current_time}, 预约成功列表 {success_list}")

        if sum(success_list) == today_reservation_num:
            logging.info("全部预约成功，程序结束")
            return

        time.sleep(1)
        current_time = get_current_time(action)

def debug(users, action=False):
    logging.info(f"Debug Mode start")
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)

    current_dayofweek = get_current_dayofweek(action)
    for index, user in enumerate(users):
        username, password, times, roomid, seatid, daysofweek = user.values()
        if action:
            username, password = usernames.split(',')[index], passwords.split(',')[index]

        if current_dayofweek not in daysofweek:
            continue

        s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
        s.get_login_status()
        s.login(username, password)
        s.requests.headers.update({'Host': 'office.chaoxing.com'})
        s.submit(times, roomid, seatid, action)

def get_roomid(args1, args2):
    username = input("请输入用户名：")
    password = input("请输入密码：")
    s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
    s.get_login_status()
    s.login(username=username, password=password)
    s.requests.headers.update({'Host': 'office.chaoxing.com'})
    encode = input("请输入deptldEnc：")
    s.roomid(encode)

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    parser = argparse.ArgumentParser(prog='Chao Xing seat auto reserve')
    parser.add_argument('-u','--user', default=config_path, help='user config file')
    parser.add_argument('-m','--method', default="reserve", choices=["reserve", "debug", "room"], help='for debug')
    parser.add_argument('-a','--action', action="store_true", help='use --action to enable in github action')
    args = parser.parse_args()

    func_dict = {"reserve": main, "debug": debug, "room": get_roomid}
    with open(args.user, "r+") as data:
        usersdata = json.load(data)["reserve"]
    func_dict[args.method](usersdata, args.action)

