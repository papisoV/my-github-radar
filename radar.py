import requests
import datetime
import os

# --- 1. 配置区 ---
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK')
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

    # 过滤出真正“新鲜”的项目
    new_items = [item for item in items if str(item['id']) not in pushed_ids]

    if not new_items:
        print("没有检测到未推送的新增项目。")
        exit(0)

    # --- 4. 构造并写入 README.md (保持显示前 15 个最火的) ---
    md_content = f"# 🌊 GitHub 暗流监控报告\n\n> 更新时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    for item in items[:15]:
        md_content += f"### ⭐ {item['stargazers_count']} | [{item['full_name']}]({item['html_url']})\n"
        md_content += f"- **简介**: {item['description'] or '暂无描述'}\n\n"

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # --- 5. 推送新项目并更新 ID 记录 ---
    if FEISHU_WEBHOOK:
        card_elements = []
        # 只推送前 5 个真正新鲜的项目，防止单次推送过多
        for item in new_items[:5]:
            card_elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**✨ 发现新暗流** | [{item['full_name']}]({item['html_url']})\n**Stars**: {item['stargazers_count']}\n{item['description'] or '无描述'}"
                }
            })
            card_elements.append({"tag": "hr"})
            # 记录此 ID
            pushed_ids.add(str(item['id']))

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "🚀 GitHub 新增暗流项目"},
                    "template": "orange"
                },
                "elements": card_elements
            }
        }
        requests.post(FEISHU_WEBHOOK, json=payload)

    # 将更新后的 ID 列表写回文件
    with open(DB_FILE, "w") as f:
        for _id in pushed_ids:
            f.write(f"{_id}\n")

except Exception as e:
    print(f"执行出错: {e}")
