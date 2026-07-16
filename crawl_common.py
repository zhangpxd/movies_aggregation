"""crawl_common.py —— 6 个数据源脚本共用的"增量续抓"工具。

核心能力:
- load_state:  加载流地址验证状态; 对本地已有流地址但无记录的条目播种为"现在已验证",
               避免首次部署时把所有历史条目都重抓一遍(一次性大回刷)。
- need_detail: 判断某条目是否还需抓详情/流地址。True=需抓, False=可跳过。
               - 全新条目(本地无)         -> True
               - 缺流地址                 -> True
               - 流地址已验证且未超期     -> False(跳过)
               - 流地址已超期(默认 7 天)  -> True(定期回刷)
- mark_verified: 记录某条目流地址的验证时间。
- save_state:   原子写状态文件。

状态文件: data/_crawl_state.json  { "<id>": "YYYY-MM-DD HH:MM:SS", ... }
不写入对外主数据, 前端展示不受影响。
"""
import json, os, datetime

STATE_FILE = 'data/_crawl_state.json'
REFRESH_DAYS = 7  # 流地址定期回刷周期(天)


def now_dt():
    return datetime.datetime.now()


def now_iso():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _parse(t):
    try:
        return datetime.datetime.strptime(t, '%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def load_state(path=STATE_FILE, videos=None):
    """加载状态。若传入 videos(本地数据列表或 {id:item} 字典),
    对已有流地址但无状态的条目播种为'现在已验证'(首跑不触发全量回刷)。"""
    state = {}
    if os.path.exists(path):
        try:
            state = json.load(open(path, encoding='utf-8'))
        except Exception:
            state = {}
    if videos is not None:
        now = now_iso()
        items = videos.values() if isinstance(videos, dict) else videos
        for v in items:
            vid = v.get('id')
            if vid is None:
                continue
            if v.get('streamUrl') and str(vid) not in state:
                state[str(vid)] = now
    return state


def need_detail(vid, item, state, refresh_days=REFRESH_DAYS, now=None):
    """是否仍需抓取详情/流地址。True=需要抓, False=可跳过。"""
    vid = str(vid)
    if item is None:
        return True  # 全新条目
    if not item.get('streamUrl'):
        return True  # 缺流地址, 必须补
    t = state.get(vid)
    if t is None:
        return True  # 无验证记录(仅首跑未播种时发生)
    pt = _parse(t)
    if pt is None:
        return True
    if now is None:
        now = now_dt()
    return (now - pt).days >= refresh_days


def mark_verified(state, vid, now=None):
    if now is None:
        now = now_iso()
    state[str(vid)] = now


def save_state(state, path=STATE_FILE):
    tmp = path + '.tmp'
    json.dump(state, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
    os.replace(tmp, path)
