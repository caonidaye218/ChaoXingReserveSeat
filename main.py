import json
import time
import argparse
import os
import logging
import datetime
import pytz
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 日志记录配置 ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- 从 utils 导入必要的模块 ---
from utils import reserve, get_user_credentials

# --- 🔥 全局配置 (已根据你的要求更新) ---
SLEEPTIME = 0.8         # 每次抢座的间隔
LOGIN_TIME = "21:58:30" # 提前登录时间
RESERVE_TIME = "22:00:00" # 准点开始抢座的时间
ENDTIME = "22:02:00"    # 延长抢座时间窗口
ENABLE_SLIDER = True    # 🔥 必须启用滑块验证码处理
MAX_ATTEMPT = 8         # 🔥 大幅增加尝试次数
RESERVE_NEXT_DAY = False # 实验版：预约当天座位

# --- 时间处理函数 ---
def get_current_time():
    """获取当前的北京时间 H:M:S"""
    return datetime.datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%H:%M:%S")

def get_current_dayofweek():
    """获取当前是星期几 (英文)"""
    return datetime.datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%A")

def wait_until(target_time_str):
    """等待直到指定的北京时间"""
    logging.info(f"等待直到北京时间 {target_time_str}...")
    while get_current_time() < target_time_str:
        time.sleep(0.1)
    logging.info(f"已到达指定时间 {target_time_str}，继续执行。")


# --- 核心逻辑函数 ---

def login_user(username, password):
    """为单个用户登录并返回 reserve 实例"""
    logging.info(f"----------- 🔐 正在登录用户 {username} -----------")
    try:
        s = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=RESERVE_NEXT_DAY,
        )
        login_success, msg = s.login(username, password)
        if not login_success:
            logging.error(f"❌ 用户 {username} 登录失败: {msg}")
            return None
        logging.info(f"✅ 用户 {username} 登录成功。")
        return s
    except Exception as e:
        logging.error(f"💥 用户 {username} 登录过程中发生异常: {e}")
        return None

def login_all_users(users, usernames_env, passwords_env, action):
    """并发登录所有用户并缓存会话实例"""
    session_cache = {}
    
    # 根据模式确定账号密码来源
    if not action:
        usernames_list = [u.get('username') for u in users]
        passwords_list = [u.get('password') for u in users]
    else:
        usernames_list = usernames_env.split(',')
        passwords_list = passwords_env.split(',')

    if len(usernames_list) != len(users) or len(passwords_list) != len(users):
        logging.error("❌ 账号/密码数量与配置文件中的用户数不匹配！")
        return {}

    # 使用线程池并发登录
    with ThreadPoolExecutor(max_workers=min(len(users), 5)) as executor:
        future_to_user = {
            executor.submit(login_user, u, p): users[i]["username"]
            for i, (u, p) in enumerate(zip(usernames_list, passwords_list))
        }
        for future in as_completed(future_to_user):
            username = future_to_user[future]
            session = future.result()
            if session:
                session_cache[username] = session
    
    logging.info(f"🎯 登录流程结束，共 {len(session_cache)} 个用户成功登录。")
    return session_cache

def process_user_tasks(session, user_config, action):
    """为一个用户处理其所有预约任务"""
    username = user_config.get('username')
    current_day = get_current_dayofweek()
    
    # 筛选出当天需要执行的任务
    tasks_to_run = [
        task for task in user_config.get('tasks', []) if current_day in task.get('daysofweek', [])
    ]
    
    if not tasks_to_run:
        logging.info(f"📅 用户 {username}: 今天没有需要执行的预约任务。")
        return True

    logging.info(f"📋 用户 {username}: 今天有 {len(tasks_to_run)} 个任务需要执行。")
    
    all_tasks_successful = True
    for i, task in enumerate(tasks_to_run):
        times = task.get('time')
        roomid = task.get('roomid')
        seatid = task.get('seatid')
        
        logging.info(f"--- 🚀 开始为用户 {username} 执行第{i+1}个任务: 时间 {times}, 房间 {roomid}, 座位 {seatid} ---")
        
        success = session.submit(times, roomid, seatid, action)
        if not success:
            all_tasks_successful = False
            logging.error(f"❌ 用户 {username} 的第{i+1}个任务失败！")
        else:
            logging.info(f"✅ 用户 {username} 的第{i+1}个任务成功！")
            # 如果一个任务成功，可以根据需要决定是否继续下一个任务
            # 当前逻辑是继续尝试预约其他时间段
            
    return all_tasks_successful


def main(users, action=False):
    """主执行函数，包含定时逻辑"""
    logging.info("🎬 程序启动...")
    
    # 1. 等待到登录时间
    wait_until(LOGIN_TIME)
    
    # 2. 登录所有用户
    usernames_env, passwords_env = get_user_credentials(action)
    session_cache = login_all_users(users, usernames_env, passwords_env, action)

    if not session_cache:
        logging.critical("💀 没有任何用户登录成功，程序终止。")
        return

    # 3. 等待到抢座时间
    wait_until(RESERVE_TIME)

    logging.info("========== 🎯 开始执行预约任务 ==========")
    
    # 4. 并发执行所有用户的任务
    with ThreadPoolExecutor(max_workers=len(users)) as executor:
        future_to_user = {
            executor.submit(process_user_tasks, session, user, action): user.get('username')
            for user in users if (session := session_cache.get(user.get('username')))
        }
        
        for future in as_completed(future_to_user):
            username = future_to_user[future]
            try:
                result = future.result()
                if result:
                    logging.info(f"🎉 用户 {username} 的所有任务处理完毕。")
                else:
                    logging.warning(f"⚠️ 用户 {username} 的部分或全部任务处理失败。")
            except Exception as e:
                logging.error(f"💥 处理用户 {username} 的任务时发生严重异常: {e}")

    logging.info("========== 🏁 所有预约任务处理完毕 ==========")


def debug(users, action=False):
    """调试模式，立即执行一次完整的登录和预约流程"""
    logging.info("--- 🔧 调试模式启动 ---")
    
    # 调试模式下不等待，直接执行
    usernames_env, passwords_env = get_user_credentials(action)
    session_cache = login_all_users(users, usernames_env, passwords_env, action)

    if not session_cache:
        logging.critical("💀 调试失败：没有任何用户登录成功。")
        return

    for user in users:
        username = user.get('username')
        session = session_cache.get(username)
        if session:
            process_user_tasks(session, user, action)

    logging.info("--- 🔧 调试模式结束 ---")


if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    parser = argparse.ArgumentParser(prog='超星座位自动预约')
    parser.add_argument('-u', '--user', default=config_path, help='用户配置文件路径')
    parser.add_argument('-m', '--method', default="reserve", choices=["reserve", "debug"], help='运行模式: reserve (定时) 或 debug (立即)')
    parser.add_argument('-a', '--action', action="store_true", help='启用 GitHub Actions 模式')
    args = parser.parse_args()
    
    try:
        with open(args.user, "r", encoding="utf-8") as data:
            # 🔥 注意：这里的配置文件结构和我之前版本不同，需要适配
            # 假设你的配置文件结构是 {"reserve": [{"username": ..., "tasks": [...]}]}
            usersdata = json.load(data).get("reserve", [])
        logging.info(f"📚 成功加载 {len(usersdata)} 个用户配置。")
    except Exception as e:
        logging.error(f"💥 配置文件加载失败: {e}")
        exit(1)
    
    if args.method == "reserve":
        main(usersdata, args.action)
    else:
        debug(usersdata, args.action)
