import os
import json
import time
import random
import sys
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
  "分享好书",
  "阅读习惯养成记",
  "励志正能量",
  "别担心一切会慢慢好起来",
  "反内耗",
  "感想",
  "人生流淌在文字里",
  "读书的力量",
  "为什么读书",
  "同频共振",
  "寻找答案",
  "内心世界",
  "人生支点",
  "坚持读书",
  "心得",
  "自我",
  "星星之火可以燎原",
  "值得阅读的好书",
  "读书博主",
  "RED解忧书店",
  "必读书籍",
  "阅读书单",
  "推荐书单",
  "书荒焦虑求推荐",
  "书单",
  "423世界读书日",
  "世界读书日",
  "书香节",
  "余华",
  "拒绝内耗",
  "财商",
  "搞钱",
  "觉醒开悟",
  "财富思维",
  "钝感的力量",
  "感性与理性",
  "钝感力也是一种幸福的能力",
  "人格魅力是最大魅力",
  "钝感力又人格独立",
  "敏感性人格",
  "敏感人需要钝感力",
  "人格魅力能量学",
  "培养钝感力",
  "一起读好书",
  "与内心的敏感和解",
  "情绪感染力",
  "自我效能感",
  "职场进阶指南",
  "身弱",
  "中考加油",
  "高考冲刺",
  "专插本上岸",
  "文案",
  "直播创业",
  "读书会",
  "时刻警醒自己",
  "学会保护自己",
  "1年1度购物狂欢",
  "小红书买到的年度草单",
  "来一次圣地巡礼",
  "神奇的东方诗画",
  "小红书艺术发光计划",
  "亲爱的新同学",
  "2025开学季",
  "留子整活大赛",
  "女性必看",
  "DanceON时刻",
  "100件恢复能量的小事",
  "FLOW疗愈节",
  "天涯live共此时",
  "人生中场而已",
  "当我成为中年人",
  "中年人怎么了",
  "新手爸妈枕边书",
  "家居作者扶持计划",
  "今日宜整理",
  "家的养成计划",
  "秋色入我家",
  "潮流POI",
  "没有天赋那就反复",
  "我的天赋进化史",
  "自媒体干货分享",
  "如何做博主",
  "治愈书单",
  "智慧人生",
  "与自己和解",
  "和过去的自己和解",
  "钝感力",
  "阅读习惯",
  "书引力",
  "自卑与超越",
  "纯真与勇敢",
  "书海无疾苦",
  "读书的意义",
  "书荒推荐",
  "读书推荐",
  "董宇辉",
  "朝花夕拾",
  "名著",
  "平凡的世界读后感",
  "读书伴我成长",
  "平凡的世界平凡的你",
  "平凡的世界读书笔记",
  "平凡的世界",
  "路遥",
  "更好的自己",
  "刻意练习",
  "高效学习知识",
  "高效读书",
  "读书心得",
  "格局",
  "做人做事",
  "书房",
  "喝茶",
  "文学书单",
  "淡人日常",
  "鲨鱼菲特",
  "鲨鱼菲特咖啡",
  "自然要读苏",
  "放假计划",
  "享受独处",
  "新中式书房",
  "新中式",
  "墨白深度书旅",
  "精读好书",
  "富人思维",
  "助眠",
  "拥有被讨厌的勇气",
  "倾听的力量",
  "活着",
  "好書推薦",
  "活好当下",
  "读书目的和前提",
  "读书的目的",
  "读书改变命运",
  "读书的作用",
  "经典文学名著",
  "读书为了什么",
  "演讲口才",
  "文学的力量",
  "思想碰撞",
  "病隙碎笔",
  "身体和灵魂",
  "哲学",
  "听书打卡",
  "语感",
  "打卡",
  "好句分享",
  "做自己的摆渡人",
  "不断提升自己",
  "思维方式",
  "读书感悟",
  "顶级思维",
  "每日文摘",
  "多读书少走弯路",
  "知识就是财富",
  "努力永远都不晚",
  "相信自己",
  "发光发亮的自己",
  "你想活出怎样的人生",
  "活出自己想要的样子",
  "被文字所感动",
  "买书",
  "我会被文字打动",
  "蛤蟆先生去看心理医生",
  "5分钟田野",
  "书单分享",
  "社会学",
  "自学",
  "AI",
    ]
    query_num = 20
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
        stop_due_to_failures = False
        for i in range(len(query)):
            #for i in range(15, 16, 1):
            try:
                note_urls, success, msg, merged_path, comment_failures = data_spider.spider_some_search_note(
                    query[i], query_num, cookies_str, base_path, 'all',
                    sort_type_choice, note_type, note_time, note_range, pos_distance, geo=None
                )
            except RuntimeError as e:
                print(f"评论抓取失败次数过多，终止爬取: {e}")
                stop_due_to_failures = True
                break
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
                    # 仅在评论抓取失败时记录到待补齐列表
                    if comment_failures > 0:
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
        if stop_due_to_failures:
            sys.exit(1)
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
