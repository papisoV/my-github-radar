import requests
import datetime
import os

# --- 1. 配置区 ---
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK')
PUSHDEER_KEY = "PDU38939T9Wp8bt11RTZPCi5FkYaV24vJjCzfXu28"
DB_FILE = "pushed_ids.txt"

# 【自定义精细化配置】
LANG_PREFERENCE = ""  # 如果想看特定语言可填，如 "python" 或 "rust"，留空看全类目
BLACK_LIST = ["awesome", "roadmap", "interview", "collection", "guide", "free-courses"] # 排除资料集

# --- 2. 读取已推送的 ID 列表 ---
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        pushed_ids = set(line.strip() for line in f if line.strip())
else:
    pushed_ids = set()

# --- 3. 抓取逻辑 ---
# 计算 30 天前
start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')

# 构造 GitHub 查询语法
query = f"created:>{start_date} stars:>500 fork:false"
if LANG_PREFERENCE:
    query += f" language:{LANG_PREFERENCE}"

url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"

try:
    response = requests.get(url)
    all_items = response.json().get('items', [])
    
    if not all_items:
        print("暂时没有符合条件的项目。")
        exit(0)

    # --- 4. 多维度精筛（排除非代码项目/资料集） ---
    qualified_items = []
    for item in all_items:
        full_name = item['full_name'].lower()
        description = (item['description'] or "").lower()
        
        # 只要项目名或描述里包含黑名单词汇，直接跳过
        if any(word in full_name or word in description for word in BLACK_LIST):
            continue
        qualified_items.append(item)

    # --- 5. 更新 README.md (总是展示精筛后的前 15 个) ---
    md_content = f"# 🌊 GitHub 暗流监控报告\n\n> 过滤规则：创建 < 30天 | Stars > 500 | 排除资料集\n>\n> 最后更新：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    for item in qualified_items[:15]:
        md_content += f"### ⭐ {item['stargazers_count']} | [{item['full_name']}]({item['html_url']})\n"
        md_content += f"- **简介**: {item['description'] or '暂无描述'}\n\n"

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # --- 6. 执行增量推送 (查重逻辑) ---
    new_items = [item for item in qualified_items if str(item['id']) not in pushed_ids]

    if new_items:
        # A. 飞书卡片推送 (带热度预警样式)
        if FEISHU_WEBHOOK:
            card_elements = []
            for item in new_items[:5]:
                # 【热度预警逻辑】：如果 30 天内星数 > 2000，标记为“爆发型”
                is_explosive = item['stargazers_count'] > 2000
                prefix = "🔥 [现象级爆发]" if is_explosive else "✨ [新增暗流]"
                
                card_elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md", 
                        "content": f"**{prefix}**\n**项目**: [{item['full_name']}]({item['html_url']})\n**Stars**: `{item['stargazers_count']}`\n**简介**: {item['description'] or '无'}"
                    }
                })
                card_elements.append({"tag": "hr"})
            
            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": "🚀 GitHub 实时情报更新"},
                        "template": "orange" if any(i['stargazers_count'] > 2000 for i in new_items[:5]) else "blue"
                    },
                    "elements": card_elements
                }
            }
            requests.post(FEISHU_WEBHOOK, json=payload)

        # B. PushDeer 推送
        for item in new_items[:3]:
            text = f"GitHub暗流: {item['full_name']}"
            desp = f"Stars: {item['stargazers_count']}\n{item['description']}"
            requests.get(f"https://api2.pushdeer.com/message/push?pushkey={PUSHDEER_KEY}&text={text}&desp={desp}")

        # C. 记录 ID 并持久化
        for item in new_items:
            pushed_ids.add(str(item['id']))

        with open(DB_FILE, "w") as f:
            for _id in pushed_ids:
                f.write(f"{_id}\n")
        
        print(f"成功推送 {len(new_items)} 个新项目。")
    else:
        print("未发现未推送的新鲜暗流。")

except Exception as e:
    print(f"运行出错: {e}")
