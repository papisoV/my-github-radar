import requests
import datetime
import os
import json
import urllib.parse

# --- 1. 配置区 ---
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK')
DB_FILE = "pushed_ids.txt"
HISTORY_FILE = "stars_history.json"
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN') 

BLACK_LIST = ["awesome", "roadmap", "interview", "collection", "guide", "free-courses"]
FAMOUS_ORGS = ["vercel", "openai", "anthropic", "meta", "google", "microsoft", "bytedance", "alibaba", "xai-org", "nvidia", "cloudflare"]
GROWTH_THRESHOLD = 50  # 爆发阈值

# --- 2. 核心功能函数 ---

def get_owner_fame(owner_name):
    """识别 Owner 是否是大佬或大厂"""
    if owner_name.lower() in FAMOUS_ORGS:
        return "🏢 大厂官号"
    if GITHUB_TOKEN:
        try:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            user_url = f"https://api.github.com/users/{owner_name}/repos?sort=stars&per_page=1"
            res = requests.get(user_url, headers=headers, timeout=5).json()
            if isinstance(res, list) and len(res) > 0:
                if res[0]['stargazers_count'] > 10000:
                    return "👑 大佬回归"
        except: pass
    return ""

def get_smart_tags(item):
    """根据描述识别技术标签"""
    name_desc = (item['full_name'] + (item['description'] or "")).lower()
    tags = []
    if item['language']: tags.append(f"🏷️{item['language']}")
    topics = {
        "🤖 AI/ML": ["llm", "ai", "gpt", "claude", "agent", "rag", "inference", "stable-diffusion"],
        "🌐 Web": ["react", "vue", "typescript", "tailwind", "nextjs", "browser"],
        "⚙️ Tooling": ["cli", "workflow", "automation", "scripts"],
        "🦀 Performance": ["rust", "performance", "blazing", "cuda", "cpp"],
        "☁️ DevOps": ["docker", "k8s", "aws", "serverless", "cloudflare"]
    }
    for tag, keywords in topics.items():
        if any(key in name_desc for key in keywords): tags.append(tag)
    return " ".join(tags[:3])

def translate_to_zh(text):
    if not text: return "无描述"
    try:
        base_url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q="
        res = requests.get(base_url + urllib.parse.quote(text), timeout=5)
        return "".join([i[0] for i in res.json()[0]])
    except: return text

def get_hn_context(full_name):
    """跨界情报：搜索 Hacker News 讨论"""
    try:
        # 使用项目名搜索 HN
        query_name = full_name.split('/')[-1]
        hn_api = f"https://hn.algolia.com/api/v1/search?query={query_name}&tags=story"
        res = requests.get(hn_api, timeout=5).json()
        if res['nbHits'] > 0:
            top = res['hits'][0]
            return {
                "url": f"https://news.ycombinator.com/item?id={top['objectID']}",
                "comments": top.get('num_comments', 0),
                "points": top.get('points', 0)
            }
    except: pass
    return None

# --- 3. 数据加载 ---
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
    items = requests.get(url, headers=headers).json().get('items', [])
    if not items: exit(0)

    current_stars_map = {}
    qualified_items = []
    
    for i in items:
        if any(word in (i['full_name']+(i['description'] or "")).lower() for word in BLACK_LIST): continue

        # 活跃度过滤
        pushed_at = datetime.datetime.strptime(i['pushed_at'], '%Y-%m-%dT%H:%M:%SZ') + datetime.timedelta(hours=8)
        if (now - pushed_at).total_seconds() > 48 * 3600: continue
            
        item_id = str(i['id'])
        current_stars = i['stargazers_count']
        current_stars_map[item_id] = current_stars
        
        # 计算增长
        base_growth = current_stars - stars_history.get(item_id, current_stars)
        i['raw_growth'] = base_growth
        i['hour_growth'] = base_growth 
        
        # 识别画像
        fame_tag = get_owner_fame(i['owner']['login'])
        i['fame_tag'] = fame_tag
        i['smart_tags'] = (f"{fame_tag} " if fame_tag else "") + get_smart_tags(i)
        
        # --- 跨界联动逻辑 ---
        i['hn_info'] = None
        if base_growth > 30 or fame_tag:
            i['hn_info'] = get_hn_context(i['full_name'])
            if i['hn_info'] and i['hn_info']['comments'] > 10:
                i['hour_growth'] += 2000 # 极客热议大幅加权
                i['smart_tags'] += " 🔥极客热议"

        # 最终权重分配
        if fame_tag: i['hour_growth'] += 10000 
        elif current_stars > 10000 and base_growth > 30: i['hour_growth'] += 500
        
        qualified_items.append(i)

    # 排序
    sorted_items = sorted(qualified_items, key=lambda x: x['hour_growth'], reverse=True)
    explosive_items = [i for i in sorted_items if i['raw_growth'] >= GROWTH_THRESHOLD or (i['fame_tag'] and i['raw_growth'] > 20)]
    new_items = [i for i in sorted_items if str(i['id']) not in pushed_ids]

    # --- 5. README 构造 ---
    md_content = f"# 🌊 GitHub 技术暗流雷达\n\n> 🕒 更新: {now_str} | 👑=大佬 | 🌐=有跨界讨论\n\n"
    md_content += "| 增长/h | 智能标签 | 项目名称 | 总 Stars | 跨界讨论 | 中文简介 |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    
    for i in sorted_items[:15]:
        growth_style = f"**🔥 +{i['raw_growth']}**" if i['raw_growth'] >= GROWTH_THRESHOLD else f"+{i['raw_growth']}"
        desc_zh = translate_to_zh(i['description'])
        hn_link = f"[💬讨论]({i['hn_info']['url']})" if i.get('hn_info') else "--"
        md_content += f"| {growth_style} | {i['smart_tags']} | [{i['full_name']}]({i['html_url']}) | {i['stargazers_count']} | {hn_link} | {desc_zh} |\n"

    with open("README.md", "w", encoding="utf-8") as f: f.write(md_content)

    # --- 6. 飞书卡片推送 ---
    SUMMARY_HOURS = [9, 21]  
    is_summary_time = now.hour in SUMMARY_HOURS

    if is_summary_time:
        push_candidates = sorted_items[:8]
        card_title, card_template, status_prefix = "📊 GitHub 趋势汇总", "blue", "📈 Top"
    else:
        push_candidates = (explosive_items + [i for i in new_items if i not in explosive_items])[:5]
        card_title = "🛰️ 顶级技术情报"
        is_fame = push_candidates[0].get('fame_tag') if push_candidates else False
        card_template, status_prefix = ("purple" if is_fame else "orange"), ""

    if push_candidates and FEISHU_WEBHOOK:
        card_elements = []
        for idx, i in enumerate(push_candidates):
            desc_zh = translate_to_zh(i['description'])
            growth_info = f"\n🚀 **时速: +{i['raw_growth']} stars/hr**" if i['raw_growth'] > 0 else ""
            hn_text = f"\n🌐 **HN讨论**: [{i['hn_info']['points']}分/{i['hn_info']['comments']}评]({i['hn_info']['url']})" if i.get('hn_info') else ""
            
            if is_summary_time: status = f"{status_prefix} {idx+1}"
            else: status = "🚨 大佬动向" if i['fame_tag'] else ("🔴 特急爆发" if i['raw_growth'] >= GROWTH_THRESHOLD else "✨ 发现新项目")
            
            card_elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{status}** | {i['smart_tags']}\n**项目**: [{i['full_name']}]({i['html_url']})\n**总 Stars**: `{i['stargazers_count']}`{growth_info}{hn_text}\n**简介**: {desc_zh}"}
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
