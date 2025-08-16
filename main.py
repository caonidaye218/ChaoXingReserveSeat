import json
import time
import argparse
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

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
ENDTIME = "22:01:00"  # 根据学校的预约座位时间+1min即可
START_TIME = "22:00:00"  # 程序启动时间，22点准时启动

ENABLE_SLIDER = True  # 是否有滑块验证
MAX_ATTEMPT = 5  # 最大尝试次数
RESERVE_NEXT_DAY = True  # 预约明天而不是今天的
MAX_LOOP_ATTEMPTS = 3  # 最多循环尝试3次，如果3次都没有成功预约任何座位则停止


def execute_single_task(username, password, task, action, task_id):
    """执行单个任务 - 新增的并行执行函数"""
    times = task["time"]
    roomid = task["roomid"]
    seatid = task["seatid"]
    
    logging.info(f"----------- {username} -- {times} -- {seatid} try (Task {task_id}) -----------")
    
    s = reserve(
        sleep_time=SLEEPTIME,
        max_attempt=MAX_ATTEMPT,
        enable_slider=ENABLE_SLIDER,
        reserve_next_day=RESERVE_NEXT_DAY,
    )
    s.get_login_status()
    login_result = s.login(username, password)
    
    if not login_result[0]:
        logging.error(f"Login failed for {username} (Task {task_id}): {login_result[1]}")
        return False
        
    s.requests.headers.update({"Host": "office.chaoxing.com"})
    success = s.submit(times, roomid, seatid, action)
    
    if success:
        logging.info(f"✅ {username} - {times} - {seatid} SUCCESS (Task {task_id})")
    else:
        logging.info(f"❌ {username} - {times} - {seatid} FAILED (Task {task_id})")
    
    return success


def login_and_reserve(users, usernames, passwords, action, success_list=None):
    logging.info(
        f"Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_NEXT_DAY: {RESERVE_NEXT_DAY}"
    )
    
    if action and len(usernames.split(",")) != len(users):
        raise Exception("user number should match the number of config")
    
    current_dayofweek = get_current_dayofweek(action)
    
    # 🔥 新增：收集所有需要执行的任务
    all_tasks = []
    task_index = 0
    
    for index, user in enumerate(users):
        # 🔥 支持新格式 - 多任务
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
                    all_tasks.append({
                        "username": username,
                        "password": password,
                        "task": task,
                        "task_id": task_index,
                        "user_index": index
                    })
                    task_index += 1
        else:
            # 🔥 兼容旧格式 - 单任务
            username, password, times, roomid, seatid, daysofweek = user.values()
            if action:
                username, password = (
                    usernames.split(",")[index],
                    passwords.split(",")[index],
                )
            
            if current_dayofweek in daysofweek:
                # 转换为新格式
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
                    "task_id": task_index,
                    "user_index": index
                })
                task_index += 1
    
    # 初始化成功状态列表
    if success_list is None:
        success_list = [False] * len(all_tasks)
    
    # 🔥 如果没有任务需要执行
    if not all_tasks:
        logging.info("Today not set to reserve")
        return success_list
    
    # 🔥 并行执行所有任务
    max_workers = min(len(all_tasks), 3)  # 最多3个并发
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {}
        
        # 提交未完成的任务
        for task_info in all_tasks:
            if not success_list[task_info["task_id"]]:
                future = executor.submit(
                    execute_single_task,
                    task_info["username"],
                    task_info["password"],
                    task_info["task"],
                    action,
                    task_info["task_id"]
                )
                future_to_task[future] = task_info
        
        # 处理完成的任务
        for future in as_completed(future_to_task):
            task_info = future_to_task[future]
            try:
                result = future.result()
                success_list[task_info["task_id"]] = result
                
                # 添加任务间的随机延迟，避免请求过于密集
                time.sleep(random.uniform(0.1, 0.3))
                
            except Exception as e:
                logging.error(f"Task execution error for task {task_info['task_id']}: {e}")
                success_list[task_info["task_id"]] = False
    
    return success_list


def main(users, action=False):
    current_time = get_current_time(action)
    logging.info(f"Program started at {current_time}, action {'on' if action else 'off'}")
    
    # 等待启动时间
    while current_time < START_TIME:
        time.sleep(0.1)  # 避免CPU空转
        current_time = get_current_time(action)
    
    logging.info(f"🚀 Start time reached! Beginning reservation process at {current_time}")
    
    attempt_times = 0
    # 🔥 新增：连续失败计数器
    consecutive_fail_count = 0
    
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)
    success_list = None
    current_dayofweek = get_current_dayofweek(action)
    
    # 🔥 计算今天需要执行的任务总数（支持新旧格式）
    today_reservation_num = 0
    for user in users:
        if "tasks" in user:
            # 新格式：多任务
            today_reservation_num += sum(
                1 for task in user["tasks"] if current_dayofweek in task.get("daysofweek", [])
            )
        else:
            # 旧格式：单任务
            if current_dayofweek in user.get("daysofweek", []):
                today_reservation_num += 1
    
    # 🔥 如果今天没有预约任务，直接退出
    if today_reservation_num == 0:
        logging.info("Today not set to reserve, exiting...")
        return
    
    while current_time < ENDTIME and consecutive_fail_count < MAX_LOOP_ATTEMPTS:
        attempt_times += 1
        logging.info(f"🔄 Starting attempt {attempt_times} (consecutive failures: {consecutive_fail_count})")
        
        try:
            success_list = login_and_reserve(
                users, usernames, passwords, action, success_list
            )
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            consecutive_fail_count += 1
            current_time = get_current_time(action)
            logging.info(
                f"attempt time {attempt_times}, time now {current_time}, "
                f"success list {success_list}, consecutive failures: {consecutive_fail_count}"
            )
            continue
        
        current_time = get_current_time(action)
        successful_tasks = sum(success_list) if success_list else 0
        
        logging.info(
            f"attempt time {attempt_times}, time now {current_time}, "
            f"success list {success_list} ({successful_tasks}/{today_reservation_num} tasks completed)"
        )
        
        # 🔥 检查是否全部预约成功
        if success_list and successful_tasks == today_reservation_num:
            logging.info("🎉 All reservations completed successfully!")
            return
        
        # 🔥 检查本轮是否有任何成功的预约
        if success_list and successful_tasks > 0:
            # 有成功的预约，重置连续失败计数器
            consecutive_fail_count = 0
            logging.info(f"✅ Some reservations succeeded, continuing...")
        else:
            # 本轮没有任何成功的预约
            consecutive_fail_count += 1
            logging.warning(f"❌ No reservations succeeded in this attempt. Consecutive failures: {consecutive_fail_count}")
        
        # 🔥 检查是否达到最大连续失败次数
        if consecutive_fail_count >= MAX_LOOP_ATTEMPTS:
            logging.error(f"💥 Reached maximum consecutive failures ({MAX_LOOP_ATTEMPTS}). Stopping reservation attempts.")
            break
        
        # 短暂休息后继续下一轮尝试
        time.sleep(1)
    
    # 🔥 最终状态报告
    if current_time >= ENDTIME:
        logging.info("⏰ Reached end time, stopping reservation attempts.")
    
    final_success_count = sum(success_list) if success_list else 0
    if final_success_count > 0:
        logging.info(f"✅ Final result: {final_success_count}/{today_reservation_num} reservations completed successfully!")
    else:
        logging.info("❌ Final result: No reservations were successful.")


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
        # 🔥 支持新格式debug
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
            # 🔥 保持旧格式兼容
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
