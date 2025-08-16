import json
import time
import argparse
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


from utils import reserve, get_user_credentials

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


SLEEPTIME = 0.2  # 每次抢座的间隔
ENDTIME = "20:00:00"  # 根据学校的预约座位时间+1min即可

ENABLE_SLIDER = True  # 是否有滑块验证
MAX_ATTEMPT = 5  # 最大尝试次数
RESERVE_NEXT_DAY = False  # 预约明天而不是今天的


def execute_single_task(username, password, task, action):
    """执行单个任务"""
    times = task["time"]
    roomid = task["roomid"]
    seatid = task["seatid"]
    
    logging.info(f"----------- {username} -- {times} -- {seatid} try -----------")
    
    s = reserve(
        sleep_time=SLEEPTIME,
        max_attempt=MAX_ATTEMPT,
        enable_slider=ENABLE_SLIDER,
        reserve_next_day=RESERVE_NEXT_DAY,
    )
    s.get_login_status()
    login_success = s.login(username, password)
    
    if not login_success[0]:
        logging.error(f"Login failed for {username}: {login_success[1]}")
        return False
        
    s.requests.headers.update({"Host": "office.chaoxing.com"})
    success = s.submit(times, roomid, seatid, action)
    
    if success:
        logging.info(f"✅ {username} - {times} - {seatid} SUCCESS")
        return True
    else:
        logging.info(f"❌ {username} - {times} - {seatid} FAILED")
        return False


def login_and_reserve(users, usernames, passwords, action, success_list=None):
    logging.info(
        f"Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_NEXT_DAY: {RESERVE_NEXT_DAY}"
    )
    
    if action and len(usernames.split(",")) != len(users):
        raise Exception("user number should match the number of config")
    
    current_dayofweek = get_current_dayofweek(action)
    
    # 🔥 新功能：支持多任务并行处理
    all_tasks = []  # 存储所有需要执行的任务
    task_index = 0  # 任务索引，用于追踪成功状态
    
    for index, user in enumerate(users):
        # 🔥 支持新格式的config文件
        if "tasks" in user:
            # 新格式：包含多个任务
            username = user["username"]
            password = user["password"]
            
            if action:
                username, password = (
                    usernames.split(",")[index],
                    passwords.split(",")[index],
                )
            
            # 为每个任务创建独立的执行单元
            for task in user["tasks"]:
                if current_dayofweek in task["daysofweek"]:
                    all_tasks.append({
                        "username": username,
                        "password": password,
                        "task": task,
                        "original_index": index,
                        "task_index": task_index
                    })
                    task_index += 1
        else:
            # 🔥 保持对旧格式的兼容性
            username, password, times, roomid, seatid, daysofweek = user.values()
            if action:
                username, password = (
                    usernames.split(",")[index],
                    passwords.split(",")[index],
                )
            
            if current_dayofweek in daysofweek:
                # 将旧格式转换为新格式
                task = {
                    "time": times,
                    "roomid": roomid,
                    "seatid": seatid if isinstance(seatid, list) else [seatid],
                    "daysofweek": daysofweek
                }
                all_tasks.append({
                    "username": username,
                    "password": password,
                    "task": task,
                    "original_index": index,
                    "task_index": task_index
                })
                task_index += 1
    
    # 初始化成功列表
    if success_list is None:
        success_list = [False] * task_index
    
    # 🔥 并行执行所有任务
    if all_tasks:
        # 限制并发数量，避免对服务器造成过大压力
        max_workers = min(len(all_tasks), 3)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_task = {}
            for task_info in all_tasks:
                if not success_list[task_info["task_index"]]:  # 只执行未成功的任务
                    future = executor.submit(
                        execute_single_task,
                        task_info["username"],
                        task_info["password"],
                        task_info["task"],
                        action
                    )
                    future_to_task[future] = task_info
            
            # 处理完成的任务
            for future in as_completed(future_to_task):
                task_info = future_to_task[future]
                try:
                    result = future.result()
                    success_list[task_info["task_index"]] = result
                    
                    if result:
                        logging.info(f"🎉 Task completed successfully: {task_info['username']} - {task_info['task']['time']}")
                    else:
                        logging.info(f"💥 Task failed: {task_info['username']} - {task_info['task']['time']}")
                        
                except Exception as e:
                    logging.error(f"Task execution error: {e}")
                    success_list[task_info["task_index"]] = False
    
    return success_list


def main(users, action=False):
    current_time = get_current_time(action)
    logging.info(f"start time {current_time}, action {'on' if action else 'off'}")
    attempt_times = 0
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)
    success_list = None
    current_dayofweek = get_current_dayofweek(action)
    
    # 🔥 计算今天需要执行的任务总数（支持新格式）
    today_reservation_num = 0
    for user in users:
        if "tasks" in user:
            # 新格式
            today_reservation_num += sum(
                1 for task in user["tasks"] if current_dayofweek in task.get("daysofweek", [])
            )
        else:
            # 旧格式
            if current_dayofweek in user.get("daysofweek", []):
                today_reservation_num += 1
    
    while current_time < ENDTIME:
        attempt_times += 1
        # try:
        success_list = login_and_reserve(
            users, usernames, passwords, action, success_list
        )
        # except Exception as e:
        #     print(f"An error occurred: {e}")
        print(
            f"attempt time {attempt_times}, time now {current_time}, success list {success_list}"
        )
        current_time = get_current_time(action)
        if success_list and sum(success_list) == today_reservation_num:
            print(f"reserved successfully!")
            return


def debug(users, action=False):
    logging.info(
        f"Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_NEXT_DAY: {RESERVE_NEXT_DAY}"
    )
    suc = False
    logging.info(f" Debug Mode start! , action {'on' if action else 'off'}")
    if action:
        usernames, passwords = get_user_credentials(action)
    current_dayofweek = get_current_dayofweek(action)
    
    for index, user in enumerate(users):
        # 🔥 支持新格式的debug模式
        if "tasks" in user:
            username = user["username"]
            password = user["password"]
            
            if action:
                username, password = (
                    usernames.split(",")[index],
                    passwords.split(",")[index],
                )
            
            for task in user["tasks"]:
                if current_dayofweek in task["daysofweek"]:
                    times = task["time"]
                    roomid = task["roomid"]
                    seatid = task["seatid"]
                    if type(seatid) == str:
                        seatid = [seatid]
                    
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
                    if suc:
                        return
        else:
            # 🔥 保持旧格式兼容性
            username, password, times, roomid, seatid, daysofweek = user.values()
            if type(seatid) == str:
                seatid = [seatid]
            if action:
                username, password = (
                    usernames.split(",")[index],
                    passwords.split(",")[index],
                )
            if current_dayofweek not in daysofweek:
                logging.info("Today not set to reserve")
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
            if suc:
                return


def get_roomid(args1, args2):
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
        help="for debug",
    )
    parser.add_argument(
        "-a",
        "--action",
        action="store_true",
        help="use --action to enable in github action",
    )
    args = parser.parse_args()
    func_dict = {"reserve": main, "debug": debug, "room": get_roomid}
    with open(args.user, "r+") as data:
        usersdata = json.load(data)["reserve"]
    func_dict[args.method](usersdata, args.action)
