import requests
import datetime
import os

# --- 1. 配置区 ---
# 建议将这些 Key 都存放在 GitHub Secrets 中
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK')
PUSHDEER_KEY = "PDU38939T9Wp8bt11RTZPCi5FkYaV24vJjCzfXu28" # 你提供的 Key
DB_FILE = "pushed_ids.txt"

# --- 2. 读取已推送的 ID 列表 ---
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        pushed_ids = set(line.strip() for line in f if line.strip())
else:
    pushed_ids = set()

# --- 3. 抓取逻辑 ---
start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
query = f"created:>{start_date} stars:>500 fork:false"
url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"

try:
    response = requests.get(url)
    items = response.json().get('items', [])
    
    if not items:
        print("暂时没有符合条件的新项目。")
        exit(0)

    # 过滤出未推送过的新增项目
    new_items = [item for item in items if str(item['id']) not in pushed_ids]

    # --- 4. 更新 README.md (总是展示当前最火的 15 个) ---
    md_content = f"# 🌊 GitHub 暗流监控报告\n\n> 最后更新：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    for item in items[:15]:
        md_content += f"### ⭐ {item['stargazers_count']} | [{item['full_name']}]({item['html_url']})\n"
        md_content += f"- **简介**: {item['description'] or '暂无描述'}\n\n"

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # --- 5. 执行推送逻辑 (仅针对新项目) ---
    if new_items:
        # A. 飞书卡片推送
        if FEISHU_WEBHOOK:
            card_elements = []
            for item in new_items[:5]: # 限制单次卡片项目数
                card_elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**✨ 发现新暗流** | [{item['full_name']}]({item['html_url']})\n**Stars**: {item['stargazers_count']}"}
                })
            
            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"tag": "plain_text", "content": "🚀 GitHub 新增暗流"}, "template": "orange"},
                    "elements": card_elements
                }
            }
            requests.post(FEISHU_WEBHOOK, json=payload)

        # B. PushDeer 推送
        for item in new_items[:3]: # PushDeer 建议只推最火的前几个，避免手机连环震动
            text = f"GitHub暗流: {item['full_name']}"
            desp = f"Stars: {item['stargazers_count']}\n简介: {item['description']}\n链接: {item['html_url']}"
            push_url = f"https://api2.pushdeer.com/message/push?pushkey={PUSHDEER_KEY}&text={text}&desp={desp}"
            requests.get(push_url)

        # C. 记录新推送的 ID
        for item in new_items:
            pushed_ids.add(str(item['id']))

        # 更新 ID 数据库文件
        with open(DB_FILE, "w") as f:
            for _id in pushed_ids:
                f.write(f"{_id}\n")
        
        print(f"成功推送 {len(new_items)} 个新项目。")
    else:
        print("没有检测到新增项目，不触发推送。")

except Exception as e:
    print(f"运行出错: {e}")
