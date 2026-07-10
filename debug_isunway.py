import requests, re, json, time
from collections import Counter

H={'User-Agent':'Mozilla/5.0','Accept':'text/html','Accept-Language':'zh-CN'}
B='https://isunway.com'
sess=requests.Session()
sess.get(B+'/',headers=H,timeout=15)
time.sleep(0.5)

# 测试播放页
r=sess.get(B+'/index.php?m=vod-play-id-3-src-1-num-1',headers=H,timeout=15)
t=r.text

# 找所有js文件
js_files=re.findall(r'src="([^"]+)"',t)
player_js=[j for j in js_files if 'layer' in j.lower() or 'mac' in j.lower()]
print(f"JS files: {player_js[:5]}")

# 内嵌JS
scripts=re.findall(r'<script[^>]*>([\s\S]*?)</script>',t)
for s in scripts:
    s=s.strip()
    if len(s)>50 and any(k in s for k in ['url','m3u8','player','play','vod','src']):
        # 关键行
        lines=[l.strip() for l in s.split('\n') if any(k in l for k in ['url','m3u8','mp4','src','play'])]
        if lines:
            print(f"JS lines: {lines[:5]}")

# MacPlayer配置
mac_config=re.findall(r'MacPlayer[^;]*;',t)
if mac_config:
    print(f"MacPlayer: {mac_config[0][:200]}")

# 搜索所有域名
all_urls=re.findall(r'https?://[a-zA-Z0-9][^\x00-\x20"<>]+',t)
m3u8_urls=[u for u in all_urls if '.m3u8' in u]
print(f"m3u8 in page: {len(m3u8_urls)}")
mp4_urls=[u for u in all_urls if '.mp4' in u]
print(f"mp4 in page: {len(mp4_urls)}")

# 找所有包含数字ID的链接
id_links=re.findall(r'/(\d+)[^\"]*html',t)
print(f"ID links: {list(set(id_links))[:10]}")

# 找包含 api 的链接
api_links=re.findall(r'/api[^\"]*',t)
print(f"API links: {api_links[:5]}")

# meta
meta_content=re.findall(r'<meta[^>]+content="([^"]+)"',t)
print(f"Meta: {meta_content[:3]}")
