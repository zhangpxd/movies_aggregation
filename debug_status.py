import requests, re, json

H = {'User-Agent':'Mozilla/5.0','Accept':'text/html','Accept-Language':'zh-CN'}

# 1. mediavip - 跟元数据爬虫完全一致的请求方式
with open('E:/new_video/data/full_videos.json','r') as f: d=json.load(f)
tv_vids = [v['id'] for v in d['videos'] if v['category']=='tv'][:5]
mv_vids = [v['id'] for v in d['videos'] if v['category']=='movie'][:2]

print('=== mediavip splay ===')
for vid in mv_vids + tv_vids:
    r = requests.get(f'https://www.mediavip.cn/splay/{vid}-1-1/', headers=H, timeout=15)
    t = r.text
    # 检查是否被Cloudflare拦截
    cf = 'Just a moment' in t or 'cf-browser-verify' in t
    # 找视频标题
    title = re.search(r'<title>([^<]+)', t)
    # 找视频源
    src = re.search(r'videoSrc\s*=\s*"([^"]+)"', t) 
    # 找剧集/状态
    ep_matches = re.findall(r'(?:更新|全|第|HD|TC|连载|完结)[^<>]{0,20}', t[:5000])
    status = [e.strip() for e in ep_matches if len(e.strip())>2]
    
    print(f'  {vid}: CF={cf} title={title.group(1)[:40] if title else "?"} src={bool(src)} status={status[:3]}')

# 2. 12ju - 细节页和视频页
print('\n=== 12ju ===')
with open('E:/new_video/data/12ju.json','r') as f: d2=json.load(f)
tv12 = [v['id'] for v in d2['videos'] if v['category']=='tv'][:5]

s = requests.Session()
s.get('https://v.12ju.com/', headers=H, timeout=15)
for vid in tv12:
    for url in [f'https://v.12ju.com/tv/{vid}.html', f'https://v.12ju.com/video/{vid}-2-1.html']:
        r = s.get(url, headers=H, timeout=15)
        t = r.text
        cf = '502' in t[:50]
        title = re.search(r'<title>([^<]+)', t)
        ep_matches = re.findall(r'(?:更新|全|第|集|连载|完结)[^<>]{0,20}', t[:5000])
        status = [e.strip() for e in ep_matches if len(e.strip())>2]
        print(f'  {vid} ({url.split("/")[-1]}): 502={cf} title={title.group(1)[:50] if title else "?"} status={status[:3]}')
    break
