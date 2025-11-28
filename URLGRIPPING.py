import os
import json
import time
import random
from main import Data_Spider, AdaptiveLimiter
from xhs_utils.common_util import init

if __name__ == '__main__':
    """
        此文件为爬虫的入口文件，可以直接运行
        apis/xhs_pc_apis.py 为爬虫的api文件，包含小红书的全部数据接口，可以继续封装
        apis/xhs_creator_apis.py 为小红书创作者中心的api文件
        感谢star和follow
    """

    cookies_str, base_path = init()
    data_spider = Data_Spider()
    # 运行模式：
    #   crawl         爬取帖子详情+评论，生成合并JSON
    #   fill_comments 从上次生成的合并JSON（列表文件）中读取并补齐所有评论，写回原JSON
    RUN_MODE = os.environ.get('XHS_RUN_MODE', 'crawl').strip().lower()
    pending_list_path = os.path.join(base_path['excel'], 'pending_comments.json')
    
    # 3 搜索指定关键词的笔记
    query = [
        "视频", "美食", "旅行", "体育", "游戏", "健身塑型", "搞笑", "学习",
        "科学科普", "艺术", "情感", "社科", "职场", "户外", "读书", "汽车",
        "科技数码", "摄影", "绘画", "动漫", "家具", "心理", "音乐", "穿搭",
        "机车", "竞技体育", "篮球"
    ]
    query_num = 1
    new_query = []
    sort_type_choice = 0  # 0 综合排序, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
    note_type = 1 # 0 不限, 1 视频笔记, 2 普通笔记
    note_time = 0  # 0 不限, 1 一天内, 2 一周内天, 3 半年内
    note_range = 0  # 0 不限, 1 已看过, 2 未看过, 3 已关注
    pos_distance = 0  # 0 不限, 1 同城, 2 附近 指定这个1或2必须要指定 geo
    seen = set()
    # 跨运行去重：加载历史已抓取的 note_id
    visited_path = os.path.join(base_path['excel'], 'visited_note_ids.json')
    try:
        if os.path.exists(visited_path):
            with open(visited_path, 'r', encoding='utf-8') as f:
                prev = json.load(f)
                if isinstance(prev, list):
                    seen.update(prev)
    except Exception as e:
        print(f"读取历史去重列表失败: {e}")
    if RUN_MODE == 'crawl':
        #for i in range(len(query)):
        for i in range(15, 16, 1):
            note_urls, success, msg, merged_path = data_spider.spider_some_search_note(
                query[i], query_num, cookies_str, base_path, 'all',
                sort_type_choice, note_type, note_time, note_range, pos_distance, geo=None
            )
            # 节流：每轮关键词间随机等待
            time.sleep(random.uniform(3.0, 6.0))
            # 每处理若干关键词做一次长休眠
            if (i + 1) % 5 == 0:
                cool = random.uniform(40, 80)
                print(f"批量节流：休眠 {int(cool)}s 以降低频次风险 ...")
                time.sleep(cool)
            # 从本次合并JSON提取 tags 并累加到 new_query
            try:
                if isinstance(merged_path, str) and os.path.exists(merged_path):
                    # 记录到待补齐列表
                    try:
                        if os.path.exists(pending_list_path):
                            with open(pending_list_path, 'r', encoding='utf-8') as f:
                                pendings = json.load(f) or []
                        else:
                            pendings = []
                        if merged_path not in pendings:
                            pendings.append(merged_path)
                            with open(pending_list_path, 'w', encoding='utf-8') as f:
                                json.dump(pendings, f, ensure_ascii=False, indent=2)
                            print(f"已加入待补齐评论队列: {merged_path}")
                    except Exception as e:
                        print(f"更新待补齐列表失败: {e}")
                    with open(merged_path, 'r', encoding='utf-8') as f:
                        items = json.load(f)
                    for it in (items or []):
                        for tg in (it.get('tags') or []):
                            if tg and tg not in seen:
                                seen.add(tg)
                                new_query.append(tg)
                else:
                    # 兼容：如果未返回合并路径，可忽略本轮
                    pass
            except Exception as e:
                print(f"解析标签失败: {e}")
    elif RUN_MODE == 'fill_comments':
        # 读取待补齐列表，逐个补齐评论
        try:
            if os.path.exists(pending_list_path):
                with open(pending_list_path, 'r', encoding='utf-8') as f:
                    pendings = json.load(f) or []
            else:
                pendings = []
        except Exception as e:
            print(f"读取待补齐列表失败: {e}")
            pendings = []
        if not pendings:
            print("待补齐评论列表为空，无需执行。")
        else:
            for p in list(pendings):
                ok, msg, cnt = data_spider.fill_comments_for_merged_json(p, cookies_str)
                print(f"更新 {p}: {ok}, {msg}")
                # 轻微等待避免频次
                time.sleep(random.uniform(2.0, 4.0))
            # 清空队列（简单策略：全部尝试后清空）
            try:
                with open(pending_list_path, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                print(f"已清空待补齐列表: {pending_list_path}")
            except Exception as e:
                print(f"清空待补齐列表失败: {e}")
    # 可选：将 new_query 落地，便于后续复用
    try:
        out_path = os.path.join(base_path['excel'], 'new_query.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(new_query, f, ensure_ascii=False, indent=2)
        print(f"已生成 new_query，共 {len(new_query)} 个标签，保存至: {out_path}")
    except Exception as e:
        print(f"保存 new_query 失败: {e}")
    # 持久化已抓取的 note_id 列表
    try:
        with open(visited_path, 'w', encoding='utf-8') as f:
            json.dump(sorted(list(seen)), f, ensure_ascii=False, indent=2)
        print(f"已更新去重列表，共 {len(seen)} 条，保存至: {visited_path}")
    except Exception as e:
        print(f"保存去重列表失败: {e}")
