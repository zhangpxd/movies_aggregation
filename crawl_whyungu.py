"""crawl_whyungu.py —— 龙腾源整合抓取脚本(单文件产出)。

把原来分散的 mac_scraper(列表+详情) / fetch_streams(抓流) / merge_streams(合并)
整合为一个入口, 最终只保留一份可用主文件 data/whyungu.json(含列表/海报/详情/年份/分类/状态/流地址)。

依赖(均为项目保留的核心模块, 不可删):
  mac_scraper.py  -> 列表+详情(写入 data/whyungu.json)
  fetch_streams.py-> 抓流(写入 data/whyungu_streams_cp.json + data/whyungu_streams.json)
  merge_streams.py-> 由检查点合并

用法:
  python crawl_whyungu.py all       # 完整管线: 列表+详情 -> 抓流 -> fold 为单文件
  python crawl_whyungu.py list      # 仅列表+详情(写 data/whyungu.json)
  python crawl_whyungu.py stream    # 仅抓流(写检查点+streams.json)
  python crawl_whyungu.py fold      # 把流合并进 data/whyungu.json 并删除冗余 streams.json/cp.json
  python crawl_whyungu.py smoke:10  # 冒烟: 取前 10 条验证连通+字段解析, 写 data/whyungu_smoke.json(不改生产数据)
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mac_scraper as ms
import fetch_streams as fs
from datetime import datetime

NAME = 'whyungu'
LABEL = '龙腾'
BASE = 'https://www.whyungu.com'
WORKERS = 5

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
MAIN = os.path.join(DATA, f'{NAME}.json')
STREAMS = os.path.join(DATA, f'{NAME}_streams.json')
CP = os.path.join(DATA, f'{NAME}_streams_cp.json')
SMOKE = os.path.join(DATA, f'{NAME}_smoke.json')
VERSIONS = os.path.join(DATA, 'versions.json')


def fold():
    """把流检查点合并进主文件, 删除冗余 streams.json / cp.json, 更新 versions.json。"""
    if not os.path.exists(MAIN):
        print(f'[fold] 缺少 {MAIN}, 请先跑 list/stream'); return
    if not os.path.exists(CP):
        print(f'[fold] 缺少 {CP}(流检查点), 无法合并流; 仅保留主列表文件')
        return
    main = json.load(open(MAIN, encoding='utf-8'))
    done = json.load(open(CP, encoding='utf-8'))
    videos = main.get('videos', [])
    id2v = {v['id']: v for v in videos}
    n_stream = 0
    for vid, st in done.items():
        v = id2v.get(vid)
        if not v:
            continue
        v['streams'] = st
        if st:
            first = st[0]['url'] if isinstance(st[0], dict) else st[0]
            v['streamUrl'] = first or ''
            n_stream += 1
    main['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json.dump(main, open(MAIN, 'w', encoding='utf-8'), ensure_ascii=False)
    for f in (STREAMS, CP):
        if os.path.exists(f):
            os.remove(f)
            print(f'[fold] 已删除冗余文件 {os.path.basename(f)}')
    versions = {}
    try:
        versions = json.load(open(VERSIONS, encoding='utf-8'))
    except Exception:
        pass
    versions[f'data/{NAME}.json'] = {'updated': main['updated_at']}
    versions.pop(f'data/{NAME}_streams.json', None)
    json.dump(versions, open(VERSIONS, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'[fold] ✅ 合并完成: 有流 {n_stream} 条 -> {os.path.basename(MAIN)} (单文件) | versions.json 已更新')


def smoke(n=10):
    """冒烟测试: 验证源站连通 + 列表/详情/流解析是否正常, 写 _smoke.json(不改生产)。"""
    print(f'>>> [{LABEL}] 冒烟测试 前 {n} 条 {datetime.now():%H:%M:%S}')
    html = ms.fetch(f'{BASE}/vodshow/1-----------.html')
    conn = bool(html and len(html) > 500)
    items = ms.parse_list(html) if html else []
    sample = items[:n]
    print(f'    列表连通: {conn} | 解析到影片ID: {len(items)}')
    rows = []
    for it in sample:
        vid = it['id']
        url = it.get('url') or f'{BASE}/voddetail/{vid}.html'
        dh = ms.fetch(url)
        info = ms.parse_detail(dh, it) if dh else {}
        streams = fs.get_streams_for(url) if dh else []
        rows.append({
            'id': vid, 'title': info.get('title', it.get('title')),
            'year': info.get('year', ''), 'poster': bool(info.get('poster')),
            'subcat': info.get('subcat', ''), 'desc_len': len(info.get('desc', '') or ''),
            'stream_count': len(streams),
            'first_stream': (streams[0]['url'] if streams and isinstance(streams[0], dict) else '')[:80],
        })
        print(f'    {vid} {info.get("title","")[:20]!r} 年={info.get("year","")} 海报={bool(info.get("poster"))} 子类={info.get("subcat","")} 流={len(streams)}')
    report = {
        'source': BASE, 'mode': 'smoke', 'n': n,
        'connectivity': conn, 'list_parsed': len(items),
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'sample': rows,
    }
    json.dump(report, open(SMOKE, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'>>> [{LABEL}] 冒烟报告 -> {os.path.basename(SMOKE)}')


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else 'all').lower()
    if mode == 'list':
        ms.run_source(NAME, LABEL, BASE, WORKERS)
    elif mode == 'stream':
        fs.run_source(NAME, LABEL, WORKERS)
    elif mode == 'fold':
        fold()
    elif mode.startswith('smoke'):
        n = 10
        if ':' in mode:
            try:
                n = int(mode.split(':', 1)[1])
            except Exception:
                pass
        smoke(n)
    elif mode == 'all':
        print(f'>>> [{LABEL}] 完整管线启动 {datetime.now():%H:%M:%S}')
        ms.run_source(NAME, LABEL, BASE, WORKERS)
        fs.run_source(NAME, LABEL, WORKERS)
        fold()
        print(f'>>> [{LABEL}] 完整管线结束 {datetime.now():%H:%M:%S}')
    else:
        print('用法: python crawl_whyungu.py [all|list|stream|fold|smoke:N]')
        sys.exit(1)


if __name__ == '__main__':
    main()
