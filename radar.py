import requests
import datetime
import os
import json
import urllib.parse

# --- 1. 配置区 ---
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK')
DB_FILE = "pushed_ids.txt"
HISTORY_FILE = "stars_history.json"
# 强烈建议在 GitHub Secrets 中配置 MY_GITHUB_TOKEN
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN') 

BLACK_LIST = ["awesome", "roadmap", "interview", "collection", "guide", "free-courses"]
# 知名大厂/机构名单
FAMOUS_ORGS = ["vercel", "openai", "anthropic", "meta", "google", "microsoft", "bytedance", "alibaba", "xai-org", "nvidia", "cloudflare"]
GROWTH_THRESHOLD = 50  # 爆发阈值：50 stars/hr

# --- 2. 核心功能函数 ---

def get_owner_fame(owner_name):
    """识别 Owner 是否是大佬或大厂"""
    if owner_name.lower() in FAMOUS_ORGS:
        return "🏢 大厂官号"
    
    if GITHUB_TOKEN:
        try:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            # 查询作者最火的项目，判断其实力
            user_url = f"https://api.github.com/users/{owner_name}/repos?sort=stars&per_page=1"
            res = requests.get(user_url, headers=headers, timeout=5).json()
            if isinstance(res, list) and len(res) > 0:
                if res[0]['stargazers_count'] > 10000:
                    return "👑 大佬回归"
        except:
            pass
    return ""

def get_smart_tags(item):
    """根据项目描述自动识别技术标签"""
    name_desc = (item['full_name'] + (item['description'] or "")).lower()
    tags = []
    if item['language']:
        tags.append(f"🏷️{item['language']}")
    
    topics = {
        "🤖 AI/ML": ["llm", "ai", "gpt", "claude", "agent", "rag", "inference", "stable-diffusion"],
        "🌐 Web/Frontend": ["react", "vue", "typescript", "tailwind", "nextjs", "browser"],
        "⚙️ Tooling": ["cli", "workflow", "automation", "scripts"],
        "🦀 Performance": ["rust", "performance", "blazing", "cuda", "cpp"],
        "☁️ DevOps": ["docker", "k8s", "aws", "serverless", "cloudflare"]
    }
    for tag, keywords in topics.items():
        if any(key in name_desc for key in keywords):
            tags.append(tag)
    return " ".join(tags[:3])

def translate_to_zh(text):
    """简单的 Google 翻译接口，用于翻译项目简介"""
    if not text: return "无描述"
    try:
        base_url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q="
        res = requests.get(base_url + urllib.parse.quote(text), timeout=5)
        return "".join([i[0] for i in res.json()[0]])
    except:
        return text

# --- 3. 时间与数据加载 ---
# 关键：修正为北京时间 (UTC+8)
now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
now_str = now.strftime('%Y-%m-%d %H:%M:%S')

pushed_ids = set()
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        pushed_ids = set(line.strip() for line in f if line.strip())

stars_history = {}
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r") as f:
        try: stars_history = json.load(f)
        except: stars_history = {}

# --- 4. 抓取与处理 ---
start_date = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
query = f"created:>{start_date} stars:>500 fork:false"
url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"

try:
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    response = requests.get(url, headers=headers)
    items = response.json().get('items', [])
    if not items: exit(0)

    current_stars_map = {}
    qualified_items = []
    
    for i in items:
        # 黑名单过滤
        if any(word in (i['full_name']+(i['description'] or "")).lower() for word in BLACK_LIST):
            continue
            
        item_id = str(i['id'])
        current_stars = i['stargazers_count']
        current_stars_map[item_id] = current_stars
        
        # 计算增长时速
        base_growth = 0
        if item_id in stars_history:
            base_growth = current_stars - stars_history[item_id]
        
        # 识别大佬
        fame_tag = get_owner_fame(i['owner']['login'])
        
        # 存储原始数据和权重数据
        i['raw_growth'] = base_growth
        i['hour_growth'] = base_growth 
        if fame_tag and base_growth > 20:
             i['hour_growth'] += 10000 # 权重提拔，确保大佬项目在 README 置顶
        
        i['fame_tag'] = fame_tag
        i['smart_tags'] = (f"{fame_tag} " if fame_tag else "") + get_smart_tags(i)
        qualified_items.append(i)

    # 排序与判定
    sorted_items = sorted(qualified_items, key=lambda x: x['hour_growth'], reverse=True)
    explosive_items = [i for i in sorted_items if i['raw_growth'] >= GROWTH_THRESHOLD or (i['fame_tag'] and i['raw_growth'] > 20)]
    new_items = [i for i in sorted_items if str(i['id']) not in pushed_ids]

    # --- 5. README 构造 ---
    md_content = f"# 🌊 GitHub 技术暗流雷达 (情报员版)\n\n"
    md_content += f"> 🕒 更新: {now_str} (北京时间) | 👑 = 万星作者 | 🏢 = 核心机构\n\n"
    md_content += "| 增长/h | 智能标签 | 项目名称 | 总 Stars | 中文简介 |\n| :--- | :--- | :--- | :--- | :--- |\n"
    
    for i in sorted_items[:15]:
        growth_style = f"**🔥 +{i['raw_growth']}**" if i['raw_growth'] >= GROWTH_THRESHOLD else f"+{i['raw_growth']}"
        desc_zh = translate_to_zh(i['description'])
        md_content += f"| {growth_style} | {i['smart_tags']} | [{i['full_name']}]({i['html_url']}) | {i['stargazers_count']} | {desc_zh} |\n"

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # --- 6. 飞书卡片推送 (智能汇总模式) ---
    # 汇总时间点（北京时间 9 点和 21 点）
    SUMMARY_HOURS = [9, 21]  
    is_summary_time = now.hour in SUMMARY_HOURS

    if is_summary_time:
        push_candidates = sorted_items[:8]
        card_title = "📊 GitHub 技术趋势汇总"
        card_template = "blue"
        status_prefix = "📈 榜单 Top"
    else:
        push_candidates = explosive_items + [i for i in new_items if i not in explosive_items]
        card_title = "🛰️ 顶级技术情报"
        is_fame = push_candidates[0].get('fame_tag') if push_candidates else False
        card_template = "purple" if is_fame else "orange"
        status_prefix = ""

    if push_candidates and FEISHU_WEBHOOK:
        card_elements = []
        limit = 8 if is_summary_time else 5
        
        for idx, i in enumerate(push_candidates[:limit]):
            desc_zh = translate_to_zh(i['description'])
            growth_info = f"\n🚀 **时速: +{i['raw_growth']} stars/hr**" if i['raw_growth'] > 0 else ""
            
            if is_summary_time:
                status = f"{status_prefix} {idx+1}"
            else:
                status = "🚨 大佬动向" if i['fame_tag'] else ("🔴 特急爆发" if i['raw_growth'] >= GROWTH_THRESHOLD else "✨ 发现新项目")
            
            card_elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{status}** | {i['smart_tags']}\n**项目**: [{i['full_name']}]({i['html_url']})\n**总 Stars**: `{i['stargazers_count']}`{growth_info}\n**简介**: {desc_zh}"}
            })
            card_elements.append({"tag": "hr"})

        requests.post(FEISHU_WEBHOOK, json={
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": card_title}, "template": card_template},
                "elements": card_elements
            }
        })

    # --- 7. 持久化 ---
    for i in new_items: pushed_ids.add(str(i['id']))
    with open(DB_FILE, "w") as f:
        for _id in pushed_ids: f.write(f"{_id}\n")
    with open(HISTORY_FILE, "w") as f:
        json.dump(current_stars_map, f)

except Exception as e:
    print(f"运行出错: {e}")
