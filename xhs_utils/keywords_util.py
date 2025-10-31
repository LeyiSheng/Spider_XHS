import json
import os
import re
from typing import Dict, List, Set


def _ensure_parent(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def load_keywords_library(path: str) -> Dict:
    """
    读取关键词库JSON。
    结构建议：
    {
      "keywords": {
        "糖": {"sub_tags": [], "include_patterns": [], "exclude_patterns": []}
      }
    }
    """
    if not os.path.exists(path):
        return {"keywords": {}}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {"keywords": {}}
    data.setdefault("keywords", {})
    # 规范化每个关键词对象
    for k, v in list(data["keywords"].items()):
        if not isinstance(v, dict):
            data["keywords"][k] = {"sub_tags": []}
        data["keywords"][k].setdefault("sub_tags", [])
        data["keywords"][k].setdefault("include_patterns", [])
        data["keywords"][k].setdefault("exclude_patterns", [])
        data["keywords"][k].setdefault("tag_counts", {})
    return data


def save_keywords_library(path: str, data: Dict):
    _ensure_parent(path)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _match_any(patterns: List[str], text: str) -> bool:
    for p in patterns or []:
        try:
            if re.search(p, text):
                return True
        except re.error:
            # 无效正则则按精确子串匹配
            if p in text:
                return True
    return False


def filter_tags_for_keyword(tags: List[str], keyword: str, include_patterns: List[str], exclude_patterns: List[str]) -> List[str]:
    result: List[str] = []
    for t in tags or []:
        if not t:
            continue
        t = t.strip()
        if not t or t == keyword:
            continue
        if exclude_patterns and _match_any(exclude_patterns, t):
            continue
        if include_patterns:
            if _match_any(include_patterns, t):
                result.append(t)
        else:
            result.append(t)
    # 去重，保持顺序
    seen: Set[str] = set()
    deduped = []
    for t in result:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped


def merge_sub_tags(library_keyword_obj: Dict, new_tags: List[str]):
    """
    合并到子库：更新 sub_tags 列表并统计 tag_counts。
    """
    sub_tags: List[str] = library_keyword_obj.get("sub_tags", [])
    tag_counts: Dict[str, int] = library_keyword_obj.get("tag_counts", {})

    for t in new_tags:
        if t not in sub_tags:
            sub_tags.append(t)
        tag_counts[t] = tag_counts.get(t, 0) + 1

    library_keyword_obj["sub_tags"] = sub_tags
    library_keyword_obj["tag_counts"] = tag_counts

