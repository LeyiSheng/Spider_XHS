from main import Data_Spider
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
    
    # 3 搜索指定关键词的笔记
    query = ["视频", "美食", "旅行", "穿搭", "健身", "运动", "摄影", "读书", "音乐", "电影", "舞蹈", "手工", "绘画", "美妆", "护肤", "宠物", "汽车", "科技", "游戏", "动漫", "育儿", "教育", "职场", "理财", "投资", "健康", "心理", "情感", "旅游", "美食", "运动", "瑜伽", "跑步", "篮球", "足球", "羽毛球", "健身房", "减脂", "增肌", "营养餐", "户外运动", "登山", "滑雪", "冲浪", "骑行"]
    query_num = 1
    sort_type_choice = 0  # 0 综合排序, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
    note_type = 1 # 0 不限, 1 视频笔记, 2 普通笔记
    note_time = 0  # 0 不限, 1 一天内, 2 一周内天, 3 半年内
    note_range = 0  # 0 不限, 1 已看过, 2 未看过, 3 已关注
    pos_distance = 0  # 0 不限, 1 同城, 2 附近 指定这个1或2必须要指定 geo
    for i in range (len(query)):
        data_spider.spider_some_search_note(query[i], query_num, cookies_str, base_path, 'all', sort_type_choice, note_type, note_time, note_range, pos_distance, geo=None)
