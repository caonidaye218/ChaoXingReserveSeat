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


# 🚀 优化后的参数设置
SLEEPTIME = 0.1  # 从0.2减少到0.1秒，加快响应速度
ENDTIME = "22:01:00"  # 根据学校的预约座位时间+1min即可
START_TIME = "22:00:00"  # 程序启动时间，22点准时启动
PRE_LOGIN_TIME = "21:55:00"  # 🔥 新增：提前登录时间，提前5分钟登录
PRE_LOGIN_RETRY_INTERVAL = 30  # 🔥 新增：提前登录失败后重试间隔（秒）

ENABLE_SLIDER = True  # 是否有滑块验证
MAX_ATTEMPT = 3  # 从5减少到3，快速失败重试
RESERVE_NEXT_DAY = True  # 预约明天而不是今天的
MAX_LOOP_ATTEMPTS = 3  # 最多循环尝试3次，如果3次都没有成功预约任何座位则停止

# 🚀 新增成功率监控
success_rate_monitor = {
    'total_attempts': 0,
    'successful_attempts': 0,
    'start_time': None
}



def monitor_success_rate(success):
    """监控成功率"""
    success_rate_monitor['total_attempts'] += 1
    if success:
        success_rate_monitor['successful_attempts'] += 1
    
    if success_rate_monitor['total_attempts'] > 0:
        rate = success_rate_monitor['successful_attempts'] / success_rate_monitor['total_attempts'] * 100
        logging.info(f"📊 Current success rate: {rate:.1f}% ({success_rate_monitor['successful_attempts']}/{success_rate_monitor['total_attempts']})")


def pre_login_user(username, password, action):
    """🔥 新增：提前登录函数 - 仅用于预热网络连接"""
    try:
        logging.info(f"🔐 Testing login connection for user: {username}")
        
        s = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=RESERVE_NEXT_DAY,
        )
        s.get_login_status()
        login_result = s.login(username, password)
        
        if login_result[0]:
            logging.info(f"✅ Login test successful for user: {username}")
            return True
        else:
            logging.error(f"❌ Login test failed for user: {username} - {login_result[1]}")
            return False
            
    except Exception as e:
        logging.error(f"💥 Login test exception for user {username}: {e}")
        return False


def pre_login_all_users(users, usernames, passwords, action):
    """🔥 新增：批量提前登录所有用户"""
    current_time = get_current_time(action)
    
    # 等待到提前登录时间
    while current_time < PRE_LOGIN_TIME:
        remaining_time = time.strptime(PRE_LOGIN_TIME, "%H:%M:%S")
        remaining_seconds = time.mktime(remaining_time) - time.mktime(time.strptime(current_time, "%H:%M:%S"))
        
        if remaining_seconds > 30:
            time.sleep(10)  # 距离时间较远时，每10秒检查一次
        elif remaining_seconds > 1:
            time.sleep(1)   # 接近时间时，每1秒检查一次
        else:
            time.sleep(0.1) # 最后1秒内，每0.1秒检查一次
            
        current_time = get_current_time(action)
    
    logging.info(f"🔐 Pre-login time reached! Starting pre-login process at {current_time}")
    
    # 收集所有用户的登录信息
    user_credentials = []
    for index, user in enumerate(users):
        if "tasks" in user:
            username = user["username"]
            password = user["password"]
        else:
            username, password = user["username"], user["password"]
        
        if action:
            username, password = (
                usernames.split(",")[index],
                passwords.split(",")[index],
            )
        
        # 避免重复用户
        if username not in [cred[0] for cred in user_credentials]:
            user_credentials.append((username, password))
    
    # 并行执行提前登录
    max_workers = min(len(user_credentials), 6)
    logging.info(f"🔐 Login connection test using {max_workers} concurrent workers for {len(user_credentials)} users")
    
    login_retry_count = 0
    max_login_retries = 3
    total_users = len(user_credentials)
    
    while login_retry_count < max_login_retries:
        failed_users = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_user = {}
            
            for username, password in user_credentials:
                future = executor.submit(pre_login_user, username, password, action)
                future_to_user[future] = (username, password)
            
            # 处理登录结果
            for future in as_completed(future_to_user):
                username, password = future_to_user[future]
                try:
                    success = future.result()
                    if not success:
                        failed_users.append((username, password))
                except Exception as e:
                    logging.error(f"❌ Login test exception for {username}: {e}")
                    failed_users.append((username, password))
        
        # 检查登录状态
        successful_logins = total_users - len(failed_users)
        
        logging.info(f"🔐 Login test round {login_retry_count + 1}: {successful_logins}/{total_users} users tested successfully")
        
        if not failed_users:
            logging.info("🎉 All users login test completed successfully!")
            break
        
        login_retry_count += 1
        if login_retry_count < max_login_retries:
            logging.info(f"⏳ Waiting {PRE_LOGIN_RETRY_INTERVAL}s before retrying failed login tests...")
            time.sleep(PRE_LOGIN_RETRY_INTERVAL)
            user_credentials = failed_users  # 只重试失败的用户
        else:
            logging.warning(f"⚠️  Some users failed login test after {max_login_retries} attempts: {[u[0] for u in failed_users]}")
    
    return successful_logins


def execute_single_task(username, password, task, action, task_id):
    """执行单个任务 - 优化版并行执行函数"""
    times = task["time"]
    roomid = task["roomid"]
    seatid = task["seatid"]
    
    logging.info(f"🎯 {username} -- {times} -- {seatid} try (Task {task_id})")
    
    # 🚀 优化：复用session和更快的参数
    s = reserve(
        sleep_time=SLEEPTIME,
        max_attempt=MAX_ATTEMPT,
        enable_slider=ENABLE_SLIDER,
        reserve_next_day=RESERVE_NEXT_DAY,
    )
    s.get_login_status()
    login_result = s.login(username, password)
    
    if not login_result[0]:
        logging.error(f"❌ Login failed for {username} (Task {task_id}): {login_result[1]}")
        monitor_success_rate(False)
        return False
        
    s.requests.headers.update({"Host": "office.chaoxing.com"})
    success = s.submit(times, roomid, seatid, action)
    
    if success:
        logging.info(f"✅ {username} - {times} - {seatid} SUCCESS (Task {task_id})")
    else:
        logging.info(f"❌ {username} - {times} - {seatid} FAILED (Task {task_id})")
    
    monitor_success_rate(success)
    return success


def login_and_reserve(users, usernames, passwords, action, success_list=None):
    logging.info(
        f"🔧 Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_NEXT_DAY: {RESERVE_NEXT_DAY}\nPRE_LOGIN_TIME: {PRE_LOGIN_TIME}"
    )
    
    if action and len(usernames.split(",")) != len(users):
        raise Exception("user number should match the number of config")
    
    current_dayofweek = get_current_dayofweek(action)
    
    # 🔥 收集所有需要执行的任务
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
    
    # 🚀 优化：提高并发数到6个，渐进式优化
    max_workers = min(len(all_tasks), 6)  # 从3提高到6
    logging.info(f"🚀 Using {max_workers} concurrent workers for {len(all_tasks)} tasks")
    
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
                
                # 🚀 优化：减少任务间的延迟
                time.sleep(random.uniform(0.02, 0.08))  # 从0.1-0.3减少到0.02-0.08
                
            except Exception as e:
                logging.error(f"❌ Task execution error for task {task_info['task_id']}: {e}")
                success_list[task_info["task_id"]] = False
                monitor_success_rate(False)
    
    return success_list


def main(users, action=False):
    # 🚀 初始化成功率监控
    success_rate_monitor['start_time'] = time.time()
    
    current_time = get_current_time(action)
    logging.info(f"🚀 Program started at {current_time}, action {'on' if action else 'off'}")
    
    # 🔥 新增：提前登录阶段
    if current_time < PRE_LOGIN_TIME:
        logging.info(f"⏰ Waiting for pre-login time: {PRE_LOGIN_TIME}")
        
        usernames, passwords = None, None
        if action:
            usernames, passwords = get_user_credentials(action)
        
        # 执行提前登录测试
        successful_pre_logins = pre_login_all_users(users, usernames, passwords, action)
        logging.info(f"🔐 Login connection test completed: {successful_pre_logins} users tested successfully")
    else:
        logging.warning(f"⚠️  Current time ({current_time}) is past login test time ({PRE_LOGIN_TIME}), skipping login test")
    
    # 🚀 优化：更精确的等待启动时间
    current_time = get_current_time(action)
    while current_time < START_TIME:
        remaining_time = time.strptime(START_TIME, "%H:%M:%S")
        remaining_seconds = time.mktime(remaining_time) - time.mktime(time.strptime(current_time, "%H:%M:%S"))
        
        if remaining_seconds > 1:
            time.sleep(0.5)  # 每0.5秒检查一次
        else:
            time.sleep(0.01)  # 最后1秒内精确到0.01秒
            
        current_time = get_current_time(action)
    
    logging.info(f"🎯 Start time reached! Beginning reservation process at {current_time}")
    
    attempt_times = 0
    # 🔥 连续失败计数器
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
    
    logging.info(f"📋 Total tasks to complete today: {today_reservation_num}")
    
    while current_time < ENDTIME and consecutive_fail_count < MAX_LOOP_ATTEMPTS:
        attempt_times += 1
        attempt_start_time = time.time()
        logging.info(f"🔄 Starting attempt {attempt_times} (consecutive failures: {consecutive_fail_count})")
        
        try:
            success_list = login_and_reserve(
                users, usernames, passwords, action, success_list
            )
        except Exception as e:
            logging.error(f"💥 An error occurred: {e}")
            consecutive_fail_count += 1
            current_time = get_current_time(action)
            logging.info(
                f"attempt time {attempt_times}, time now {current_time}, "
                f"success list {success_list}, consecutive failures: {consecutive_fail_count}"
            )
            continue
        
        current_time = get_current_time(action)
        successful_tasks = sum(success_list) if success_list else 0
        attempt_duration = time.time() - attempt_start_time
        
        logging.info(
            f"⏱️  Attempt {attempt_times} completed in {attempt_duration:.2f}s, time now {current_time}, "
            f"success list {success_list} ({successful_tasks}/{today_reservation_num} tasks completed)"
        )
        
        # 🔥 检查是否全部预约成功
        if success_list and successful_tasks == today_reservation_num:
            total_duration = time.time() - success_rate_monitor['start_time']
            logging.info(f"🎉 All reservations completed successfully in {total_duration:.2f}s!")
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
            
            # 🚀 优化：如果连续失败，检查成功率
            if consecutive_fail_count >= 2:
                current_rate = (success_rate_monitor['successful_attempts'] / 
                                max(success_rate_monitor['total_attempts'], 1) * 100)
                if current_rate < 10:  # 成功率低于10%
                    logging.warning(f"⚠️  Low success rate detected ({current_rate:.1f}%), consider adjusting parameters")
        
        # 🔥 检查是否达到最大连续失败次数
        if consecutive_fail_count >= MAX_LOOP_ATTEMPTS:
            logging.error(f"💥 Reached maximum consecutive failures ({MAX_LOOP_ATTEMPTS}). Stopping reservation attempts.")
            break
        
        # 🚀 优化：动态调整休息时间
        if consecutive_fail_count == 0:
            time.sleep(0.5)  # 成功时短暂休息
        else:
            time.sleep(1)    # 失败时稍长休息
    
    # 🔥 最终状态报告
    total_duration = time.time() - success_rate_monitor['start_time']
    
    if current_time >= ENDTIME:
        logging.info("⏰ Reached end time, stopping reservation attempts.")
    
    final_success_count = sum(success_list) if success_list else 0
    final_success_rate = (success_rate_monitor['successful_attempts'] / 
                          max(success_rate_monitor['total_attempts'], 1) * 100)
    
    if final_success_count > 0:
        logging.info(f"✅ Final result: {final_success_count}/{today_reservation_num} reservations completed successfully in {total_duration:.2f}s!")
    else:
        logging.info(f"❌ Final result: No reservations were successful in {total_duration:.2f}s.")
    
    logging.info(f"📊 Overall success rate: {final_success_rate:.1f}% ({success_rate_monitor['successful_attempts']}/{success_rate_monitor['total_attempts']})")


def debug(users, action=False):
    logging.info(
        f"🔧 Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_NEXT_DAY: {RESERVE_NEXT_DAY}\nPRE_LOGIN_TIME: {PRE_LOGIN_TIME}"
    )
    suc = False
    logging.info(f"🐛 Debug Mode start! , action {'on' if action else 'off'}")
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
                    
                    logging.info(f"🎯 {username} -- {times} -- {seatid} try")
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
                        logging.info("✅ Debug reservation successful!")
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
            logging.info(f"🎯 {username} -- {times} -- {seatid} try")
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
                logging.info("✅ Debug reservation successful!")
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
    parser = argparse.ArgumentParser(prog="Chao Xing seat auto reserve - Optimized Version with Pre-Login")
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
    
    logging.info("🚀 Starting optimized seat reservation system with pre-login...")
    func_dict[args.method](usersdata, args.action)
