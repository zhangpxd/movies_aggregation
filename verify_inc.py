"""verify_inc.py —— 验证增量续抓逻辑的两端:
(A) 源里"全新"的 id  -> cc.need_detail 必须为 True(会被抓)
(B) 本地已有且流新鲜的 id -> cc.need_detail 必须为 False(被跳过)
做法: 拉取片多多每个分类第1页(新内容在顶部), 与本地比对, 统计两端判定。
"""
import os, sys, json, time, requests, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_common as cc
import crawl_jieshui8 as m

sess = requests.Session()


def parse_page1(slug):
    try:
        r = sess.get(f'{m.BASE}/vodtype/{slug}.html', headers=m.H, timeout=20)
        r.encoding = 'utf-8'
        if r.status_code == 200:
            return m.parse_list(r.text)
    except Exception:
        pass
    return []


def main():
    id2v = m.load_existing()
    state = cc.load_state(videos=list(id2v.values()))
    print(f'本地条目: {len(id2v)}  状态记录: {len(state)}')

    new_ids, known_ids = [], []
    for slug, cat_id, subcat in m.SUBS:
        vids = parse_page1(slug)
        for v in vids:
            vid = v['id']
            (new_ids if vid not in id2v else known_ids).append(vid)
        time.sleep(0.1)

    new_ids = list(dict.fromkeys(new_ids))      # 去重
    known_ids = list(dict.fromkeys(known_ids))

    print(f'\n[拉取] 12 个分类第1页共出现 {len(new_ids)+len(known_ids)} 条唯一id')
    print(f'  - 全新(本地无): {len(new_ids)} 个 -> {new_ids[:10]}')
    print(f'  - 已知(本地有): {len(known_ids)} 个')

    # (A) 全新条目必须 need_detail == True
    new_should_fetch = [vid for vid in new_ids if cc.need_detail(vid, None, state)]
    print(f'\n[A] 全新条目中 need_detail=True(会抓流) = {len(new_should_fetch)}/{len(new_ids)}')

    # (B) 已知条目分两类:
    #   - 有流地址 -> 应跳过(need_detail=False)
    #   - 缺流地址 -> 应补抓(need_detail=True, 这是预期行为, 不算异常)
    sample = known_ids[:200]
    has_stream = [vid for vid in sample if id2v.get(vid, {}).get('streamUrl')]
    miss_stream = [vid for vid in sample if not id2v.get(vid, {}).get('streamUrl')]
    skip_ok = [vid for vid in has_stream if not cc.need_detail(vid, id2v.get(vid), state)]
    refill_ok = [vid for vid in miss_stream if cc.need_detail(vid, id2v.get(vid), state)]
    print(f'[B] 已知抽样 {len(sample)}: 有流 {len(has_stream)} (应跳过 {len(skip_ok)}), '
          f'缺流 {len(miss_stream)} (应补抓 {len(refill_ok)})')

    ok = (len(new_should_fetch) == len(new_ids)) and \
         (len(has_stream) == 0 or len(skip_ok) == len(has_stream)) and \
         (len(miss_stream) == 0 or len(refill_ok) == len(miss_stream))
    print('\n结论:', '✅ 增量判定正确(新抓/旧跳/缺流补)' if ok else '❌ 判定异常, 需排查')
    if new_ids:
        print('   全新id示例:', new_ids[:5], '-> 这些会走抓流流程, 其余全部跳过')


if __name__ == '__main__':
    main()
