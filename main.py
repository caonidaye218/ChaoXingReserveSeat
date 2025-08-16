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

# --- 从 utils 导入必要的模块 ---
from utils import reserve, get_user_credentials

# --- 🔥 全局配置 (已根据你的要求更新) ---
SLEEPTIME = 0.8         # 每次抢座的间隔
ENDTIME = "22:02:00"    # 延长抢座时间窗口
ENABLE_SLIDER = True    # 🔥 必须启用滑块验证码处理
MAX_ATTEMPT = 8         # 🔥 大幅增加尝试次数
RESERVE_NEXT_DAY = False # 实验版：预约当天座位

# --- 时间处理函数 ---
# 保留你原有的时间获取方式
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

# --- 核心逻辑函数 (保留分流机制) ---

def login_and_reserve(users, usernames, passwords, action, success_list=None):
    """
    保留了原有的循环尝试机制，并为每个用户独立创建 reserve 实例。
    """
    if success_list is None:
        success_list = [False] * len(users)
        
    current_dayofweek = get_current_dayofweek(action)

    for index, user_config in enumerate(users):
        # 如果该用户已预约成功，则跳过
        if success_list[index]:
            continue

        # � 改为通过键名获取，更稳定
        username = user_config.get("username")
        password = user_config.get("password")
        times = user_config.get("time")
        roomid = user_config.get("roomid")
        seatid = user_config.get("seatid")
        daysofweek = user_config.get("daysofweek")

        # 如果在 Actions 模式，从 Secrets 获取账号密码
        if action:
            try:
                username = usernames.split(",")[index]
                password = passwords.split(",")[index]
            except IndexError:
                logging.error(f"❌ Actions Secrets 中的账号/密码数量与用户配置数量不匹配 (用户索引: {index})")
                continue

        # 检查今天是否需要预约
        if current_dayofweek not in daysofweek:
            logging.info(f"📅 用户 {username}: 今天不在预约日期列表中，跳过。")
            # 将不需要预约的也标记为“成功”，以防主循环卡住
            success_list[index] = True
            continue

        logging.info(f"----------- 🚀 用户 {username} | 时间 {times} | 座位 {seatid} | 开始尝试 -----------")
        
        try:
            # 为每个用户创建独立的会话实例
            s = reserve(
                sleep_time=SLEEPTIME,
                max_attempt=MAX_ATTEMPT,
                enable_slider=ENABLE_SLIDER,
                reserve_next_day=RESERVE_NEXT_DAY,
            )
            
            # 登录
            login_success, msg = s.login(username, password)
            if not login_success:
                logging.error(f"❌ 用户 {username} 登录失败: {msg}")
                continue # 登录失败，尝试下一个用户

            # 提交预约
            submit_success = s.submit(times, roomid, seatid, action)
            if submit_success:
                logging.info(f"🎉 用户 {username} 预约成功！")
                success_list[index] = True
            else:
                logging.warning(f"⚠️ 用户 {username} 本次尝试失败，将在下一轮重试。")

        except Exception as e:
            logging.error(f"💥 处理用户 {username} 时发生未知异常: {e}")
            
    return success_list


def main(users, action=False):
    """主执行函数，保留了 while 循环的分流预约机制"""
    current_time = get_current_time(action)
    logging.info(f"🎬 程序启动... | 当前时间: {current_time} | Actions模式: {'开启' if action else '关闭'}")
    
    usernames, passwords = "", ""
    if action:
        usernames, passwords = get_user_credentials(action)
        if not usernames or not passwords:
            logging.critical("💀 Actions Secrets 未配置，程序终止。")
            return

    attempt_times = 0
    success_list = None
    
    # 计算当天需要预约的总任务数
    current_dayofweek = get_current_dayofweek(action)
    today_reservation_num = sum(1 for u in users if current_dayofweek in u.get("daysofweek", []))
    
    if today_reservation_num == 0:
        logging.info("🌟 今天没有需要执行的预约任务，程序结束。")
        return

    # 🔥 核心循环，实现分流预约
    while get_current_time(action) < ENDTIME:
        attempt_times += 1
        logging.info(f"========== 🔄 第 {attempt_times} 轮抢座开始 ==========")
        
        success_list = login_and_reserve(
            users, usernames, passwords, action, success_list
        )
        
        successful_count = sum(1 for s in success_list if s)
        logging.info(
            f"本轮结果: {successful_count}/{today_reservation_num} 个任务成功 | "
            f"当前时间: {get_current_time(action)}"
        )
        
        # 如果所有任务都成功，提前结束
        if successful_count >= today_reservation_num:
            logging.info("✅ 所有预约任务均已成功！程序结束。")
            return
        
        # 等待一小段时间再进行下一轮
        time.sleep(random.uniform(1, 3))

    logging.warning(f"🏁 抢座时间已过 ({ENDTIME})，程序结束。")


def debug(users, action=False):
    """调试模式，执行一次完整的预约流程"""
    logging.info("--- 🔧 调试模式启动 ---")
    usernames, passwords = "", ""
    if action:
        usernames, passwords = get_user_credentials(action)
    
    # 在调试模式下，直接调用一次 login_and_reserve
    login_and_reserve(users, usernames, passwords, action)
    
    logging.info("--- 🔧 调试模式结束 ---")


if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    parser = argparse.ArgumentParser(prog='超星座位自动预约')
    parser.add_argument('-u', '--user', default=config_path, help='用户配置文件路径')
    parser.add_argument('-m', '--method', default="reserve", choices=["reserve", "debug"], help='运行模式: reserve 或 debug')
    parser.add_argument('-a', '--action', action="store_true", help='启用 GitHub Actions 模式')
    args = parser.parse_args()
    
    try:
        with open(args.user, "r", encoding="utf-8") as data:
            usersdata = json.load(data)["reserve"]
        logging.info(f"📚 成功加载 {len(usersdata)} 个用户配置。")
    except Exception as e:
        logging.error(f"💥 配置文件加载失败: {e}")
        exit(1)
    
    if args.method == "reserve":
        main(usersdata, args.action)
    else:
        debug(usersdata, args.action)
�
