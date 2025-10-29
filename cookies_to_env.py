import os
import re


def _strip_wrapping_quotes(s: str) -> str:
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return s


def read_cookies_txt(path: str) -> list:
    """读取 cookies.txt，返回 (key, value) 列表，不做转义。"""
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    pairs = []
    # 如果文件是单行且包含分号且包含等号，直接按分号拆
    single = ' '.join(l.strip() for l in lines).strip()
    if single.lower().startswith('cookie:'):
        single = single.split(':', 1)[1].strip()
    if (';' in single) and ('=' in single) and len(lines) == 1:
        for chunk in single.split(';'):
            chunk = chunk.strip()
            if not chunk:
                continue
            if '=' in chunk:
                k, v = chunk.split('=', 1)
                pairs.append((k.strip(), v.strip()))
        return pairs

    # 常见格式: 每行  key<TAB/SPACE>"value"  或  key=value
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if s.lower().startswith('cookie:'):
            s = s.split(':', 1)[1].strip()
        # key=value 形式
        if '=' in s and s.find('=') < s.find(' '):
            k, v = s.split('=', 1)
            pairs.append((k.strip(), _strip_wrapping_quotes(v.strip())))
            continue
        # key  "value" 或 key  'value'
        m = re.match(r"^(\S+)\s+(.+)$", s)
        if m:
            k, v = m.group(1), m.group(2).strip()
            v = _strip_wrapping_quotes(v)
            # 去掉内容中的反斜杠转义（如 \" -> ")
            v = v.replace('\"', '"').replace("\\'", "'")
            pairs.append((k, v))
    return pairs


def join_cookie_pairs(pairs: list) -> str:
    # 拼成 "k=v; k2=v2"，不加多余反斜杠
    return '; '.join(f"{k}={v}" for k, v in pairs if k)


def to_env_line(value: str, key: str = 'COOKIES') -> str:
    # 使用单引号包裹，避免为内部双引号加反斜杠
    return f"{key}='{value}'\n"


def main():
    here = os.path.abspath(os.path.dirname(__file__))
    cookies_txt = os.path.join(here, 'cookies.txt')
    out_env = os.path.join(here, 'cookies.env')

    if not os.path.exists(cookies_txt):
        raise FileNotFoundError(f'未找到 cookies.txt: {cookies_txt}')

    pairs = read_cookies_txt(cookies_txt)
    if not pairs:
        raise ValueError('cookies.txt 内容为空，无法转换为 .env 形式')

    cookie_str = join_cookie_pairs(pairs)
    line = to_env_line(cookie_str, key='COOKIES')
    with open(out_env, 'w', encoding='utf-8') as f:
        f.write(line)

    print(f'已生成: {out_env}')
    print(line, end='')


if __name__ == '__main__':
    main()
