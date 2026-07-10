"""
流地址批量抓取脚本
从 mediavip.cn 播放页提取 m3u8 流地址，填充到 JSON
用法: python stream_scraper.py
"""

import json
import re
import time
import requests

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://www.mediavip.cn',
    'Connection': 'keep-alive',
}

INPUT_FILE = 'data/mediavip.json'
OUTPUT_FILE = 'data/mediavip.json'


def extract_stream_url(play_url):
    """从播放页提取 videoSrc"""
    try:
        r = requests.get(play_url, headers=HEADERS, timeout=15)
        r.encoding = 'utf-8'
        if r.status_code != 200:
            return None

        m = re.search(r'videoSrc\s*=\s*"([^"]+)"', r.text)
        if m:
            return m.group(1).replace(r'\/', '/')
        return None
    except Exception as e:
        return None


def extract_subcat(vid):
    """从详情页提取子分类"""
    try:
        url = f'https://www.mediavip.cn/mvip/{vid}/'
        # 标准化映射
        NORMALIZE = {'喜剧片':'喜剧','动画':'动漫电影','中国动漫':'国产动漫','电视':'其他剧'}
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = 'utf-8'
        if r.status_code != 200:
            return ''
        # 匹配 类型：</span>动作,科幻,冒险 取第一个逗号前的值
        m = re.search(r'类型[：:].*?>\s*([\u4e00-\u9fa5a-zA-Z]+)', r.text)
        if m:
            val = m.group(1).strip().split(',')[0].split('，')[0].strip()
            return NORMALIZE.get(val, val)
        return ''
    except:
        return ''


def main():
    print('=' * 60)
    print('  流地址批量抓取 - mediavip.cn 播放页')
    print('=' * 60)

    # 读取现有数据
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    videos = data.get('videos', [])
    total = len(videos)
    print(f'\n  共 {total} 条视频，开始抓取流地址...\n')

    updated = 0
    skipped = 0
    failed = 0

    for i, v in enumerate(videos):
        vid = v['id']
        # 跳过已有 streamUrl 的，但检查子分类
        if v.get('streamUrl'):
            if not v.get('subcat'):
                subcat = extract_subcat(vid)
                if subcat:
                    v['subcat'] = subcat
            skipped += 1
            continue

        # 构造播放页 URL: /splay/{id}-1-1/
        play_url = f'https://www.mediavip.cn/splay/{vid}-1-1/'

        stream = extract_stream_url(play_url)
        if stream:
            v['streamUrl'] = stream
            # 同时提取子分类（如果没有的话）
            if not v.get('subcat'):
                subcat = extract_subcat(vid)
                if subcat:
                    v['subcat'] = subcat
            updated += 1
            icon = '✅'
        else:
            failed += 1
            icon = '❌'

        # 进度显示
        if (i + 1) % 10 == 0 or i == total - 1:
            print(f'  [{i+1}/{total}] {icon} {updated} ok, {skipped} skip, {failed} fail')

        # 礼貌延迟
        time.sleep(0.5)

    # 保存
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'\n' + '=' * 60)
    print(f'  完成！')
    print(f'  成功: {updated} | 跳过: {skipped} | 失败: {failed}')
    print(f'  已保存: {OUTPUT_FILE}')
    print('=' * 60)


if __name__ == '__main__':
    main()
